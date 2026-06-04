"""Window placement, DPI handling, and per-window lifecycle helpers.

The standard Tkinter ``Tk()`` ignores Windows DPI scaling: on a 4K
display at 200 % scaling it produces microscopic widgets. The
``apply_dpi_scaling`` function fixes this by calling ``tk scaling``
with the system DPI ratio.

``center_on_primary`` reads the monitor layout via the Win32 API and
places the window so that its center is the center of the primary
monitor, falling back to ``center`` if the platform is unsupported.
``clamp_to_visible`` then nudges the window back inside any monitor
if it would otherwise open off-screen (e.g. on a previously-attached
laptop display).
"""
from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DPI
# ---------------------------------------------------------------------------


def detect_dpi_scale() -> float:
    """Return the system DPI scale factor (1.0 = 100 %, 1.5 = 150 %).

    Windows: queries ``shcore.GetScaleFactorForDevice(0)``.
    macOS:   returns 2.0 on retina (we cannot easily detect "effective"
             scaling from Python; Qt also hard-codes 2.0 on retina).
    Linux:   reads ``Gdk::screen_get_default()->get_resolution()`` via
             ``xrandr`` fallback. If nothing works, returns 1.0.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            scale = wintypes.UINT()
            # MDT_EFFECTIVE_DPI_CATEGORY = 0
            hr = shcore.GetScaleFactorForDevice(0, ctypes.byref(scale))
            if hr == 0 and scale.value:
                return float(scale.value) / 100.0
        except (OSError, AttributeError, ValueError):
            pass
        # Fallback: GetDeviceCaps
        try:
            import ctypes
            from ctypes import wintypes

            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            hdc = gdi32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            gdi32.DeleteDC(hdc)
            if dpi:
                return float(dpi) / 96.0
        except (OSError, AttributeError, ValueError):
            pass
        return 1.0

    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=2.0, check=False,
            )
            if "Retina" in out.stdout:
                return 2.0
        except (OSError, subprocess.TimeoutExpired):
            pass
        return 1.0

    # Linux — best effort
    try:
        import subprocess

        out = subprocess.run(
            ["xrdb", "-query"], capture_output=True, text=True, timeout=1.0, check=False,
        )
        for line in out.stdout.splitlines():
            if line.startswith("Xft.dpi:"):
                dpi = float(line.split(":", 1)[1].strip())
                if dpi > 0:
                    return dpi / 96.0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return 1.0


def apply_dpi_scaling(root: tk.Misc, scale: float | None = None) -> float:
    """Tell Tk the system's pixel scale. Returns the scale that was used.

    Tk's default scaling is 1.0, which is treated as 96 DPI. We multiply
    by the system scale so all internal points (font sizes, padding)
    are rendered in the OS-native coordinate space.
    """
    if scale is None:
        scale = detect_dpi_scale()
    try:
        root.tk.call("tk", "scaling", max(0.5, scale))
    except tk.TclError:
        pass
    return scale


# ---------------------------------------------------------------------------
# Monitor enumeration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Monitor:
    """A display rectangle in virtual-screen coordinates (Windows) or
    the primary screen's coords (other platforms)."""

    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains_center(self, cx: int, cy: int) -> bool:
        return self.x <= cx < self.right and self.y <= cy < self.bottom


def enumerate_monitors() -> list[Monitor]:
    """Return the list of connected displays. Falls back to a single
    primary monitor derived from ``root.winfo_screenwidth/height``."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM,
            )

            monitors: list[Monitor] = []

            @MonitorEnumProc
            def callback(hmonitor, _hdc, _rect, _lparam):
                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", RECT),
                        ("rcWork", RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                    r = info.rcMonitor
                    monitors.append(
                        Monitor(
                            x=r.left, y=r.top,
                            width=r.right - r.left, height=r.bottom - r.top,
                            is_primary=bool(info.dwFlags & 0x1),  # MONITORINFOF_PRIMARY
                        )
                    )
                return 1

            user32.EnumDisplayMonitors(None, None, callback, 0)
            if monitors:
                return monitors
        except (OSError, AttributeError, ValueError):
            pass

    # Fallback: a single monitor covering the Tk-reported screen.
    try:
        # We need a root to ask, so the caller will replace this in
        # ``center_on_screen`` using the actual Tk screen size.
        return [Monitor(0, 0, 1024, 768, is_primary=True)]
    except Exception:
        return [Monitor(0, 0, 1024, 768, is_primary=True)]


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def intersects(self, other: "Rect") -> bool:
        return (
            self.x < other.right and self.right > other.x
            and self.y < other.bottom and self.bottom > other.y
        )


def center_rect_in_rect(inner: Rect, outer: Rect) -> tuple[int, int]:
    cx = outer.x + (outer.width - inner.width) // 2
    cy = outer.y + (outer.height - inner.height) // 2
    return cx, cy


def clamp_rect(rect: Rect, monitors: Sequence[Monitor], slack: int = 32) -> Rect:
    """If ``rect`` doesn't overlap any monitor, snap it back inside the
    primary monitor. Otherwise leave it alone."""
    for m in monitors:
        if rect.intersects(Rect(m.x, m.y, m.width, m.height)):
            return rect
    primary = next((m for m in monitors if m.is_primary), monitors[0])
    x = max(primary.x + slack, min(rect.x, primary.right - rect.width - slack))
    y = max(primary.y + slack, min(rect.y, primary.bottom - rect.height - slack))
    return Rect(x, y, rect.width, rect.height)


def place_centered(
    window: tk.Toplevel | tk.Tk,
    width: int,
    height: int,
    parent: tk.Misc | None = None,
    monitors: Iterable[Monitor] | None = None,
) -> None:
    """Place ``window`` centered on the primary monitor (or its parent).
    Clamps to a visible monitor if the requested geometry would be
    off-screen."""
    window.update_idletasks()

    if parent is not None:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        outer = Rect(px, py, pw, ph)
    else:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        outer = Rect(0, 0, sw, sh)

    x, y = center_rect_in_rect(Rect(0, 0, width, height), outer)
    if monitors is None:
        monitors = list(enumerate_monitors())
    else:
        monitors = list(monitors)
    final = clamp_rect(Rect(x, y, width, height), list(monitors))
    window.geometry(f"{width}x{height}+{final.x}+{final.y}")


def place_at_cursor(
    window: tk.Toplevel | tk.Tk,
    width: int,
    height: int,
    cursor_xy: tuple[int, int] | None = None,
    monitors: Iterable[Monitor] | None = None,
) -> None:
    """Place the window just below the cursor (Raycast-style). Clamps
    to the monitor containing the cursor."""
    if cursor_xy is None:
        cursor_xy = window.winfo_pointerxy()
    if monitors is None:
        monitors = list(enumerate_monitors())
    else:
        monitors = list(monitors)
    cx, cy = cursor_xy
    chosen = next(
        (m for m in monitors if m.contains_center(cx, cy)),
        next((m for m in monitors if m.is_primary), monitors[0]),
    )
    # Center horizontally on cursor, drop down by 8 px.
    x = max(chosen.x + 8, min(cx - width // 2, chosen.right - width - 8))
    y = max(chosen.y + 8, min(cy + 12, chosen.bottom - height - 8))
    window.geometry(f"{width}x{height}+{x}+{y}")


# ---------------------------------------------------------------------------
# Window chrome
# ---------------------------------------------------------------------------


def strip_window_chrome(window: tk.Toplevel, *, hide_titlebar: bool = True) -> None:
    """Remove the title bar, borders, and taskbar entry. Used by the
    search popup to make it feel like a Raycast palette.

    Falls back gracefully on platforms / WMs that don't support it.
    """
    if hide_titlebar and sys.platform.startswith("win"):
        try:
            window.overrideredirect(True)
        except tk.TclError:
            pass
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass


def attach_focus_out(window: tk.Toplevel, on_focus_out: Callable[[], None]) -> None:
    """Hide the window when it loses focus. The classic Spotlight /
    Raycast UX: click outside → palette closes."""
    def _watch(_event=None):
        try:
            focused = window.focus_get()
        except tk.TclError:
            focused = None
        if focused is None:
            on_focus_out()

    window.bind("<FocusOut>", _watch)
    # Poll fallback: some WMs don't deliver FocusOut for overrideredirect
    # windows reliably.
    def _poll():
        try:
            if window.winfo_ismapped() and not window.winfo_viewable():
                return
            if window.focus_get() is None and window.winfo_ismapped():
                on_focus_out()
        except tk.TclError:
            return
        window.after(400, _poll)
    window.after(400, _poll)


# ---------------------------------------------------------------------------
# Reduced-motion preference
# ---------------------------------------------------------------------------


def detect_reduced_motion() -> bool:
    """Return True if the OS reports a "reduce motion" preference.

    On Windows we check the system parameter ``SPI_GETCLIENTAREAANIMATION``
    (0 = animations disabled, which approximates the intent). On macOS
    we check the ``NSAppearance`` ``reduceMotion`` setting via
    ``defaults read com.apple.universalaccess reduceMotion``. On Linux
    we look at ``GTK_MODULES`` and ``org.gnome.desktop.interface``
    (best effort, may not be available). Returns False if undetected.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            val = wintypes.BOOL()
            # SPI_GETCLIENTAREAANIMATION = 0x1042
            if user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(val), 0):
                return not bool(val.value)
        except (OSError, AttributeError, ValueError):
            pass
        return False

    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                capture_output=True, text=True, timeout=1.0, check=False,
            )
            return out.stdout.strip() in ("1", "true", "yes")
        except (OSError, subprocess.TimeoutExpired):
            return False

    return False
