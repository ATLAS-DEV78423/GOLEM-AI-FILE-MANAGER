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
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, cast

from .ui_theme import MOTION, ease_in_cubic, ease_in_out_cubic, ease_out_back, ease_out_cubic, lerp, lerp_color


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

    def __enter__(self) -> "_Animation":
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
# Reduced-motion override (context)
# ---------------------------------------------------------------------------


@contextmanager
def reduced_motion() -> Iterator[None]:
    """Context manager that forces animations to snap. Used in tests
    and by accessibility-aware callers."""
    global MOTION
    original = MOTION.reduced_motion
    from .ui_theme import Motion
    import golem.ui_theme as _t
    _t.MOTION = Motion(reduced_motion=True)
    try:
        yield
    finally:
        _t.MOTION = Motion(reduced_motion=original)
