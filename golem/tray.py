from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def _build_icon_image(color: str = "#b87333"):
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (15, 15, 15, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill=color)
        draw.ellipse((22, 22, 42, 42), fill=(15, 15, 15, 255))
        return image
    except Exception:
        return None


def _build_busy_icon():
    """Variant used while a scan is in progress. Used as the
    base image for the gentle icon pulse — see :meth:`TrayController.set_busy`."""
    return _build_icon_image(color="#e0a060")


@dataclass
class TrayCallbacks:
    """Set of callbacks wired to tray menu items.

    All callbacks are invoked on the tray's own thread. They must be
    thread-safe and must not block; long-running work should be enqueued
    onto the application's command queue.
    """

    on_search: Callable[[], None] = lambda: None
    on_rescan: Callable[[], None] = lambda: None
    on_toggle_dry_run: Callable[[], None] = lambda: None
    on_undo: Callable[[], None] = lambda: None
    on_settings: Callable[[], None] = lambda: None
    on_open_data_folder: Callable[[], None] = lambda: None
    on_view_log: Callable[[], None] = lambda: None
    on_reset: Callable[[], None] = lambda: None
    on_check_updates: Callable[[], None] = lambda: None
    on_toggle_watcher: Callable[[], None] = lambda: None
    on_toggle_autostart: Callable[[], None] = lambda: None
    on_about: Callable[[], None] = lambda: None
    on_quit: Callable[[], None] = lambda: None

    # State queries (set by the application)
    dry_run: bool = False
    paused: bool = False
    autostart_enabled: bool = False


class TrayController:
    def __init__(self, callbacks: TrayCallbacks):
        self.callbacks = callbacks
        self._icon = None
        self._thread: threading.Thread | None = None
        self._disabled = False
        self._paused = False
        self._busy_pulse: Any = None
        self._busy_pulse_lock = threading.Lock()

    def disable(self) -> None:
        """Disable the tray entirely. ``start()`` becomes a no-op."""
        self._disabled = True

    def _set_icon_image(self, image: Any) -> None:
        """Swap the pystray icon. Safe to call from any thread; the
        assignment is atomic and pystray handles its own locking."""
        if self._icon is None or image is None:
            return
        try:
            self._icon.icon = image
        except Exception:
            pass

    def set_busy(self, busy: bool) -> None:
        """Update the tray icon to reflect scan state.

        When going busy, start a gentle color pulse on the icon so the
        user has a "working" hint beyond the static icon swap. When going
        idle, cancel any in-flight pulse and restore the dim icon.

        Both the icon swap and the pulse are best-effort; pystray
        versions vary in their support for ``Icon.icon`` and for PIL
        Image instances. Failures are swallowed silently.
        """
        with self._busy_pulse_lock:
            current = self._busy_pulse

        if not busy:
            if current is not None:
                try:
                    current.cancel()
                except Exception:
                    pass
                with self._busy_pulse_lock:
                    self._busy_pulse = None
            self._set_icon_image(_build_icon_image())
            return

        # Going busy.
        busy_image = _build_busy_icon()
        if busy_image is None:
            return
        # Set the busy icon once immediately so the user sees a change
        # even before the first pulse frame lands.
        self._set_icon_image(busy_image)

        if current is not None:
            try:
                current.cancel()
            except Exception:
                pass

        # Lazy import keeps tray importable without ui_anim (e.g. for
        # headless test runs that only need the dataclass).
        try:
            from .ui_anim import pulse_icon
        except Exception:
            return

        low_rgba: tuple[int, int, int, int] = (224, 160, 96, 255)   # matches #e0a060
        high_rgba: tuple[int, int, int, int] = (255, 200, 140, 255)  # warm peak

        try:
            pulse = pulse_icon(
                base=busy_image,
                low=low_rgba,
                high=high_rgba,
                on_frame=self._set_icon_image,
                period_ms=1400,
                step_ms=80,
            )
            with self._busy_pulse_lock:
                self._busy_pulse = pulse
        except Exception:
            # Pulse is cosmetic; never let it break the scan path.
            pass

    def notify(self, title: str, message: str) -> None:
        """Show a tray balloon / notification if the platform supports it."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title=title)
        except Exception:
            pass

    def set_paused_icon(self, paused: bool) -> None:
        """Swap to a greyed-out icon when the watcher is paused."""
        if paused:
            self._set_icon_image(_build_icon_image(color="#555555"))
        else:
            self._set_icon_image(_build_icon_image())

    def start(self) -> None:
        if self._disabled:
            return
        if self._icon is not None or self._thread is not None:
            return
        try:
            import pystray
        except Exception:
            return

        image = _build_icon_image()
        if image is None:
            return

        def _make_autostart_label() -> str:
            checked = "✓ " if self.callbacks.autostart_enabled else ""
            return f"{checked}Launch at startup"

        def _make_dry_run_label() -> str:
            checked = "✓ " if self.callbacks.dry_run else ""
            return f"{checked}Dry-run preview"

        menu = pystray.Menu(
            pystray.MenuItem("Search files", lambda _icon, _item: self.callbacks.on_search()),
            pystray.MenuItem("Re-scan watched folder", lambda _icon, _item: self.callbacks.on_rescan()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                _make_autostart_label(),
                lambda _icon, _item: self.callbacks.on_toggle_autostart(),
            ),
            pystray.MenuItem(
                _make_dry_run_label(),
                lambda _icon, _item: self.callbacks.on_toggle_dry_run(),
            ),
            pystray.MenuItem("Undo last organization", lambda _icon, _item: self.callbacks.on_undo()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", lambda _icon, _item: self.callbacks.on_settings()),
            pystray.MenuItem("Open data folder", lambda _icon, _item: self.callbacks.on_open_data_folder()),
            pystray.MenuItem("View log", lambda _icon, _item: self.callbacks.on_view_log()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for updates", lambda _icon, _item: self.callbacks.on_check_updates()),
            pystray.MenuItem("About GOLEM", lambda _icon, _item: self.callbacks.on_about()),
            pystray.MenuItem("Reset all settings", lambda _icon, _item: self.callbacks.on_reset()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda _icon, _item: self.callbacks.on_quit()),
        )
        self._icon = pystray.Icon("GOLEM", image, "GOLEM", menu)
        icon = self._icon
        assert icon is not None
        self._thread = threading.Thread(target=icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        self._icon = None
        self._thread = None

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.callbacks.on_toggle_watcher()
