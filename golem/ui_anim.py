"""Animation primitives built on ``widget.after``.

We don't pull in a 3rd-party animation library — Tk's ``after`` is
plenty fast for the durations we use (60–480 ms), and every animation
must be cancellable (popups close mid-animation, errors preempt
loaders, etc).

Public surface
--------------
- ``Animation``         — context manager that auto-cancels on exit.
- ``fade_in``           — 0 → 1 alpha on a Toplevel.
- ``fade_out_then``     — 1 → 0 alpha, then call ``then``.
- ``pulse``             — repeating opacity sine wave.
- ``slide_in``          — translate a window in from an edge.
- ``tick_dots``         — animated "..." spinner for the Test button.
- ``color_transition``  — smooth color tween between two hex values.
- ``reduced_motion``    — context flag; when set, all primitives snap.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

from .ui_theme import (
    MOTION,
    ease_in_cubic,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    lerp,
    lerp_color,
)

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancellation registry
# ---------------------------------------------------------------------------


class _Animation:
    """A cancellable animation. Yielded from every primitive; supports
    ``cancel()`` and a context manager that cancels on exit."""

    __slots__ = ("_after_id", "_widget", "_on_cancel", "_cancelled")

    def __init__(self, widget: tk.Misc, after_id: int | str | None, on_cancel: Callable[[], None] | None = None):
        self._after_id = after_id
        self._widget = widget
        self._on_cancel = on_cancel
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        try:
            if self._after_id:
                # tkinter stubs expect a str for after_cancel but runtimes
                # may return int; cast to Any to satisfy type checkers.
                self._widget.after_cancel(cast(Any, self._after_id))
        except tk.TclError:
            pass
        if self._on_cancel is not None:
            try:
                self._on_cancel()
            except Exception:
                _LOG.exception("animation cancel callback failed")

    def __enter__(self) -> _Animation:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cancel()


# ---------------------------------------------------------------------------
# Fade
# ---------------------------------------------------------------------------


def fade_in(
    window: tk.Toplevel,
    duration_ms: int | None = None,
    *,
    from_alpha: float = 0.0,
    to_alpha: float = 1.0,
    easing: Callable[[float], float] = ease_out_cubic,
    on_done: Callable[[], None] | None = None,
) -> _Animation:
    """Fade the window in by animating ``-alpha``."""
    duration = duration_ms if duration_ms is not None else MOTION.DEFAULT
    if MOTION.reduced_motion:
        duration = MOTION.instant
    state: dict[str, Any] = {"t": 0.0, "step_ms": 16, "elapsed": 0}

    try:
        window.attributes("-alpha", max(0.0, min(1.0, from_alpha)))
    except tk.TclError:
        pass

    def _step():
        if state["elapsed"] >= duration:
            try:
                window.attributes("-alpha", max(0.0, min(1.0, to_alpha)))
            except tk.TclError:
                pass
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    _LOG.exception("fade_in on_done failed")
            return
        state["elapsed"] += state["step_ms"]
        t = min(1.0, state["elapsed"] / max(1, duration))
        a = lerp(from_alpha, to_alpha, easing(t))
        try:
            window.attributes("-alpha", max(0.0, min(1.0, a)))
        except tk.TclError:
            return
        state["after_id"] = window.after(state["step_ms"], _step)

    state["after_id"] = window.after(0, _step)

    def _cancel():
        try:
            window.attributes("-alpha", max(0.0, min(1.0, to_alpha)))
        except tk.TclError:
            pass

    return _Animation(window, state["after_id"], _cancel)


def fade_out_then(
    window: tk.Toplevel,
    duration_ms: int | None = None,
    *,
    from_alpha: float | None = None,
    to_alpha: float = 0.0,
    easing: Callable[[float], float] = ease_in_cubic,
    then: Callable[[], None],
) -> _Animation:
    """Fade out, then call ``then``. The animation is auto-cancelled if
    the window is destroyed before completion."""
    duration = duration_ms if duration_ms is not None else MOTION.fast
    if MOTION.reduced_motion:
        duration = MOTION.instant
    if from_alpha is None:
        try:
            from_alpha = float(window.attributes("-alpha") or 1.0)
        except (tk.TclError, ValueError, TypeError):
            from_alpha = 1.0

    state: dict[str, Any] = {"t": 0.0, "step_ms": 16, "elapsed": 0}

    def _step():
        if state["elapsed"] >= duration:
            try:
                window.attributes("-alpha", max(0.0, min(1.0, to_alpha)))
            except tk.TclError:
                pass
            try:
                then()
            except Exception:
                _LOG.exception("fade_out_then callback failed")
            return
        state["elapsed"] += state["step_ms"]
        t = min(1.0, state["elapsed"] / max(1, duration))
        a = lerp(from_alpha, to_alpha, easing(t))
        try:
            window.attributes("-alpha", max(0.0, min(1.0, a)))
        except tk.TclError:
            return
        state["after_id"] = window.after(state["step_ms"], _step)

    state["after_id"] = window.after(0, _step)

    def _cancel():
        try:
            then()
        except Exception:
            _LOG.exception("fade_out_then cancel callback failed")

    return _Animation(window, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Slide
# ---------------------------------------------------------------------------


def slide_in(
    window: tk.Toplevel,
    *,
    duration_ms: int | None = None,
    from_dy: int = 16,
    easing: Callable[[float], float] = ease_out_back,
    on_done: Callable[[], None] | None = None,
) -> _Animation:
    """Translate the window in from below by ``from_dy`` pixels.

    Tk doesn't have a real translate transform on toplevels, so we
    animate the geometry's ``+y`` instead. The starting offset is
    applied immediately, the final offset is the window's resting y.
    """
    duration = duration_ms if duration_ms is not None else MOTION.DEFAULT
    if MOTION.reduced_motion:
        duration = MOTION.instant
    try:
        window.update_idletasks()
        geom = window.geometry()
        # "WxH+x+y"
        size, _, rest = geom.partition("+")
        x_part, _, y_part = rest.partition("+")
        x_val = int(x_part) if x_part else 0
        y_rest = int(y_part) if y_part else 0
    except (tk.TclError, ValueError):
        return _Animation(window, None)

    start_y = y_rest + from_dy
    end_y = y_rest
    state: dict[str, Any] = {"t": 0.0, "step_ms": 16, "elapsed": 0}

    try:
        window.geometry(f"{size}+{x_val}+{start_y}")
    except tk.TclError:
        return _Animation(window, "")

    def _step():
        if state["elapsed"] >= duration:
            try:
                window.geometry(f"{size}+{x_val}+{end_y}")
            except tk.TclError:
                pass
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    _LOG.exception("slide_in on_done failed")
            return
        state["elapsed"] += state["step_ms"]
        t = min(1.0, state["elapsed"] / max(1, duration))
        y = int(lerp(start_y, end_y, easing(t)))
        try:
            window.geometry(f"{size}+{x_val}+{y}")
        except tk.TclError:
            return
        state["after_id"] = window.after(state["step_ms"], _step)

    state["after_id"] = window.after(0, _step)
    return _Animation(window, state["after_id"])


# ---------------------------------------------------------------------------
# Pulse
# ---------------------------------------------------------------------------


def pulse(
    widget: tk.Misc,
    *,
    attribute: str = "foreground",
    low: str = "#7A7A85",
    high: str = "#FF8C42",
    period_ms: int = 1200,
) -> _Animation:
    """Smoothly oscillate a color attribute (e.g. foreground, background)
    between ``low`` and ``high``. Used for "scanning..." status text."""
    import math

    state: dict[str, Any] = {"t": 0.0, "step_ms": 32, "elapsed": 0, "running": True}

    def _step():
        if not state["running"]:
            return
        state["elapsed"] += state["step_ms"]
        # Sine wave 0..1
        v = 0.5 + 0.5 * math.sin(2.0 * math.pi * state["elapsed"] / period_ms)
        try:
            widget.configure(**{attribute: lerp_color(low, high, v)})
        except tk.TclError:
            state["running"] = False
            return
        state["after_id"] = widget.after(state["step_ms"], _step)

    state["after_id"] = widget.after(0, _step)

    def _cancel():
        state["running"] = False
        try:
            widget.configure(**{attribute: low})
        except tk.TclError:
            pass

    return _Animation(widget, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Color transition
# ---------------------------------------------------------------------------


def color_transition(
    widget: tk.Misc,
    *,
    attribute: str,
    from_color: str,
    to_color: str,
    duration_ms: int | None = None,
    easing: Callable[[float], float] = ease_in_out_cubic,
    on_done: Callable[[], None] | None = None,
) -> _Animation:
    """Smooth tween of a single color attribute."""
    duration = duration_ms if duration_ms is not None else MOTION.DEFAULT
    if MOTION.reduced_motion:
        duration = MOTION.instant
    state: dict[str, Any] = {"elapsed": 0, "step_ms": 16}

    def _step():
        if state["elapsed"] >= duration:
            try:
                widget.configure(**{attribute: to_color})
            except tk.TclError:
                pass
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    _LOG.exception("color_transition on_done failed")
            return
        state["elapsed"] += state["step_ms"]
        t = min(1.0, state["elapsed"] / max(1, duration))
        c = lerp_color(from_color, to_color, easing(t))
        try:
            widget.configure(**{attribute: c})
        except tk.TclError:
            return
        state["after_id"] = widget.after(state["step_ms"], _step)

    state["after_id"] = widget.after(0, _step)
    return _Animation(widget, state["after_id"])


# ---------------------------------------------------------------------------
# Tick dots — animated "Testing..." spinner
# ---------------------------------------------------------------------------


def tick_dots(
    label: tk.Misc,
    base: str = "Testing",
    interval_ms: int = 350,
    max_dots: int = 3,
) -> _Animation:
    """Animate a label's text as ``base`` + ``.`` × n, cycling 0..max_dots."""
    state: dict[str, Any] = {"n": 0, "running": True}

    def _step():
        if not state["running"]:
            return
        state["n"] = (state["n"] + 1) % (max_dots + 1)
        try:
            label.configure(text=base + "." * state["n"])
        except tk.TclError:
            state["running"] = False
            return
        state["after_id"] = label.after(interval_ms, _step)

    state["after_id"] = label.after(0, _step)

    def _cancel():
        state["running"] = False
        try:
            label.configure(text=base)
        except tk.TclError:
            pass

    return _Animation(label, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Indeterminate progress — animates a thin colored bar via
# winfo_children swap. Cheap and no PIL needed.
# ---------------------------------------------------------------------------


def indeterminate_bar(canvas: tk.Canvas, *, color: str, height: int = 2) -> _Animation:
    """Animate a thin bar across the canvas, left-to-right, looping.

    The canvas should have a fixed height; the bar is drawn as a single
    rectangle that moves with `step_ms` ticks.
    """
    state: dict[str, Any] = {"x": -120, "running": True, "step_ms": 16, "w": 100}

    def _step():
        if not state["running"]:
            return
        try:
            canvas.delete("indet")
            canvas.create_rectangle(
                state["x"], 0, state["x"] + state["w"], height,
                fill=color, outline="", tags=("indet",),
            )
        except tk.TclError:
            state["running"] = False
            return
        state["x"] += 4
        if state["x"] > canvas.winfo_width():
            state["x"] = -state["w"]
        state["after_id"] = canvas.after(state["step_ms"], _step)

    state["after_id"] = canvas.after(0, _step)

    def _cancel():
        state["running"] = False
        try:
            canvas.delete("indet")
        except tk.TclError:
            pass

    return _Animation(canvas, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Tray icon pulse — gentle "I'm working" hint on the system tray icon.
#
# Tk's ``pulse`` animates a *widget* color attribute, but a pystray icon is
# a PIL.Image held outside Tk. This primitive is the same algorithm,
# recast against PIL: it interpolates the fill color of a master image
# between ``low`` and ``high`` using a sine wave, then hands the result
# to a ``on_frame`` callback (typically ``tray.set_icon(image)``).
#
# The animation runs on the *caller's* thread (typically pystray's tray
# thread, since pystray icon swaps must happen there). We use a
# ``threading.Timer`` chain, not Tk's ``after``, because there is no
# widget to schedule against. Cancellation is driven by a ``running``
# flag plus the timer's own ``cancel()`` so we don't leak timers.
# ---------------------------------------------------------------------------


# Geometry constants for the default tray icon template. These must
# match the disc drawn in :mod:`golem.tray:_build_icon_image`. If the
# template ever changes, update these and the template together.
_TRAY_TEMPLATE_SIZE = (64, 64)
_TRAY_OUTER_ELLIPSE = (10, 10, 54, 54)
_TRAY_INNER_DOT = (22, 22, 42, 42)
_TRAY_INNER_DOT_COLOR = (15, 15, 15, 255)


def _render_tray_disc(base: Any, fill_rgba: tuple[int, int, int, int]) -> Any:
    """Repaint the disc on a copy of ``base`` (PIL.Image, RGBA).

    Kept tiny and side-effect-free so ``pulse_icon._step`` and
    ``pulse_icon._cancel`` share the exact same code path.
    """
    from PIL import ImageDraw

    frame = base.copy()
    draw = ImageDraw.Draw(frame)
    draw.ellipse(_TRAY_OUTER_ELLIPSE, fill=fill_rgba)
    draw.ellipse(_TRAY_INNER_DOT, fill=_TRAY_INNER_DOT_COLOR)
    return frame


def pulse_icon(
    *,
    base: Any,                      # PIL.Image — the icon template (RGBA)
    low: tuple[int, int, int, int], # RGBA at the dim end of the cycle
    high: tuple[int, int, int, int],
    on_frame: Callable[[Any], None],
    period_ms: int = 1400,
    step_ms: int = 80,
) -> _TimerAnimation | _Animation | _NoopAnimation:
    """Smoothly pulse the fill color of ``base`` and emit frames to ``on_frame``.

    The caller owns ``base`` — we do not mutate it. Each tick allocates a
    fresh Image (cheap for 64x64 RGBA) and hands it to ``on_frame``. The
    tray controller is expected to call ``pystray.Icon.icon = new_image``
    inside ``on_frame``.

    Returns an ``_Animation`` that, when cancelled, stops emitting frames
    and restores the icon to the ``low`` color via one final ``on_frame``
    call. Under reduced motion, returns a ``_NoopAnimation`` that just
    calls ``on_frame`` once with the ``low`` color and is otherwise inert.
    """
    import math
    import threading

    # No PIL: pulse is purely cosmetic. Return a no-op so callers can
    # still ``cancel()`` without checking.
    try:
        from PIL import Image  # noqa: F401  (import-check only)
    except ImportError:
        _LOG.debug("pulse_icon: PIL unavailable; skipping pulse")
        try:
            on_frame(_render_tray_disc(base, low) if base is not None else None)
        except Exception:
            pass
        return _NoopAnimation()

    if base is None or getattr(base, "size", None) != _TRAY_TEMPLATE_SIZE:
        _LOG.debug("pulse_icon: base size mismatch; skipping pulse")
        return _NoopAnimation()

    if MOTION.reduced_motion:
        # Snap to the dim end and stop. Don't pulse.
        try:
            on_frame(_render_tray_disc(base, low))
        except Exception:
            _LOG.exception("pulse_icon reduced-motion emit failed")
        return _NoopAnimation()

    state: dict[str, Any] = {"elapsed": 0, "running": True, "timer": None}
    lock = threading.Lock()

    def _render_frame() -> Any | None:
        """Build the next frame. Returns None on failure."""
        v = 0.5 + 0.5 * math.sin(2.0 * math.pi * state["elapsed"] / period_ms)
        low_hex = "#{:02x}{:02x}{:02x}".format(*low[:3])
        high_hex = "#{:02x}{:02x}{:02x}".format(*high[:3])
        mid_hex = lerp_color(low_hex, high_hex, v)
        # mid_hex is "#rrggbb" — parse channels directly, never int(hex).
        r = int(mid_hex[1:3], 16)
        g = int(mid_hex[3:5], 16)
        b = int(mid_hex[5:7], 16)
        return _render_tray_disc(base, (r, g, b, 255))

    def _step() -> None:
        with lock:
            if not state["running"]:
                return
            state["elapsed"] += step_ms
        try:
            frame = _render_frame()
            if frame is not None:
                on_frame(frame)
        except Exception:
            _LOG.exception("pulse_icon frame failed")
            with lock:
                state["running"] = False
            return
        with lock:
            if not state["running"]:
                return
            timer = threading.Timer(step_ms / 1000.0, _step)
            timer.daemon = True
            state["timer"] = timer
            timer.start()

    def _cancel() -> None:
        with lock:
            state["running"] = False
            timer = state.get("timer")
        if timer is not None:
            timer.cancel()
        # Restore the low color so the icon doesn't sit on a mid-frame.
        try:
            frame = _render_tray_disc(base, low)
            on_frame(frame)
        except Exception:
            _LOG.exception("pulse_icon cancel emit failed")

    timer = threading.Timer(0, _step)
    timer.daemon = True
    state["timer"] = timer
    timer.start()
    return _TimerAnimation(on_cancel=_cancel)


class _TimerAnimation:
    """An animation backed by a ``threading.Timer`` chain instead of
    ``widget.after``. The ``on_cancel`` callable is invoked when
    ``cancel()`` is called (it should set a running flag to False and
    cancel any outstanding timer).

    Provides the same interface as ``_Animation`` so callers can
    ``cancel()`` and use the context manager without branching.
    """

    __slots__ = ("_on_cancel", "_cancelled")

    def __init__(self, on_cancel: Callable[[], None] | None = None) -> None:
        self._on_cancel = on_cancel
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        if self._on_cancel is not None:
            try:
                self._on_cancel()
            except Exception:
                _LOG.exception("_TimerAnimation cancel callback failed")

    def __enter__(self) -> _TimerAnimation:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cancel()


class _NoopAnimation:
    """Returned by :func:`pulse_icon` when there's nothing to animate.

    Provides a ``cancel()`` method so callers don't need to branch.
    """

    __slots__ = ()

    def cancel(self) -> None:
        return

    def __enter__(self) -> _NoopAnimation:
        return self

    def __exit__(self, *exc: object) -> None:
        return


# ---------------------------------------------------------------------------
# Whole-app fade-out — used by the tray Quit path so the window doesn't
# vanish mid-keystroke. The caller passes the root window, the shutdown
# callable (idempotent — does the actual cleanup), and the post-shutdown
# callback (typically ``root.quit()``).
# ---------------------------------------------------------------------------


def fade_out_then_shutdown(
    window: tk.Tk | tk.Toplevel,
    *,
    shutdown: Callable[[], None],
    quit_after: Callable[[], None],
    duration_ms: int | None = None,
) -> _Animation:
    """Fade ``window`` to transparent, run ``shutdown``, then call ``quit_after``.

    Skips the animation entirely under reduced motion (snaps to 0, runs
    shutdown, quits immediately). On cancellation (e.g. user clicks Quit
    twice), runs ``shutdown`` and ``quit_after`` anyway so the process
    actually exits — a transparent window with no quit is a hang.
    """
    if MOTION.reduced_motion:
        try:
            window.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        try:
            shutdown()
        finally:
            try:
                quit_after()
            except Exception:
                _LOG.exception("quit_after failed")
        return _Animation(window, None)

    # Whole-app fade uses the default duration (200ms) — fast is too
    # snappy to register as a graceful exit.
    duration = duration_ms if duration_ms is not None else MOTION.DEFAULT
    try:
        current = float(window.attributes("-alpha") or 1.0)
    except (tk.TclError, ValueError, TypeError):
        current = 1.0
    state: dict[str, Any] = {"elapsed": 0, "step_ms": 16, "completed": False}
    lock_token: list[bool] = []  # one-shot guard for shutdown/quit_after

    def _finalize() -> None:
        if lock_token:
            return
        lock_token.append(True)
        try:
            shutdown()
        except Exception:
            _LOG.exception("shutdown failed during fade-out")
        try:
            quit_after()
        except Exception:
            _LOG.exception("quit_after failed during fade-out")

    def _step() -> None:
        if state["elapsed"] >= duration:
            try:
                window.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            _finalize()
            return
        state["elapsed"] += state["step_ms"]
        t = min(1.0, state["elapsed"] / max(1, duration))
        a = lerp(current, 0.0, ease_in_cubic(t))
        try:
            window.attributes("-alpha", max(0.0, min(1.0, a)))
        except tk.TclError:
            return
        state["after_id"] = window.after(state["step_ms"], _step)

    def _cancel() -> None:
        # On cancel (e.g. user clicks Quit twice), still finish the
        # shutdown so the process actually exits.
        _finalize()

    state["after_id"] = window.after(0, _step)
    return _Animation(window, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Shimmer skeleton — used for the "Searching..." loading state in the
# search popup. Draws a gradient sweep across a dark rectangle.
# ---------------------------------------------------------------------------


def shimmer_skeleton(
    canvas: tk.Canvas,
    *,
    x: int = 0,
    y: int = 0,
    width: int = 560,
    height: int = 44,
    base_color: str = "#16161A",
    highlight_color: str = "#1C1C22",
    period_ms: int = 1800,
) -> _Animation:
    """Animate a shimmer sweep across a rectangle. Used as a loading
    placeholder in the search popup."""
    state: dict[str, Any] = {"offset": -width, "running": True, "step_ms": 24}

    def _step():
        if not state["running"]:
            return
        try:
            canvas.delete("shimmer")
            # Base fill
            canvas.create_rectangle(
                x, y, x + width, y + height,
                fill=base_color, outline="", tags=("shimmer",),
            )
            # Sweep highlight
            sweep_w = width // 3
            sx = state["offset"]
            canvas.create_rectangle(
                sx, y, sx + sweep_w, y + height,
                fill=highlight_color, outline="", tags=("shimmer",),
            )
        except tk.TclError:
            state["running"] = False
            return
        state["offset"] += 8
        if state["offset"] > width:
            state["offset"] = -sweep_w
        state["after_id"] = canvas.after(state["step_ms"], _step)

    state["after_id"] = canvas.after(0, _step)

    def _cancel():
        state["running"] = False
        try:
            canvas.delete("shimmer")
        except tk.TclError:
            pass

    return _Animation(canvas, state["after_id"], _cancel)


# ---------------------------------------------------------------------------
# Reduced-motion override (context)
# ---------------------------------------------------------------------------


@contextmanager
def reduced_motion() -> Iterator[None]:
    """Context manager that forces animations to snap. Used in tests
    and by accessibility-aware callers."""
    global MOTION
    original = MOTION.reduced_motion
    import golem.ui_theme as _t

    from .ui_theme import Motion
    _t.MOTION = Motion(reduced_motion=True)
    try:
        yield
    finally:
        _t.MOTION = Motion(reduced_motion=original)
