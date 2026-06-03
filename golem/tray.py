from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable


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
    """Variant used while a scan is in progress. Pulses the inner dot."""
    return _build_icon_image(color="#e0a060")


def _build_idle_icon():
    """Variant used after a scan completes. Slightly darker."""
    return _build_icon_image(color="#5a3a1a")


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
    on_quit: Callable[[], None] = lambda: None


class TrayController:
    def __init__(self, callbacks: TrayCallbacks):
        self.callbacks = callbacks
        self._icon = None
        self._thread: threading.Thread | None = None
        self._disabled = False
        self._paused = False

    def disable(self) -> None:
        """Disable the tray entirely. ``start()`` becomes a no-op."""
        self._disabled = True

    def set_busy(self, busy: bool) -> None:
        """Update the tray icon to reflect scan state.

        The icon swap is best-effort; pystray versions vary in their
        support for ``Icon.icon``. If the swap fails we just keep the
        default icon and log.
        """
        if self._icon is None:
            return
        try:
            self._icon.icon = _build_busy_icon() if busy else _build_icon_image()
        except Exception:
            pass

    def notify(self, title: str, message: str) -> None:
        """Show a tray balloon / notification if the platform supports it."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title=title)
        except Exception:
            pass

    def start(self) -> None:
        if self._disabled:
            return
        try:
            import pystray
        except Exception:
            return

        image = _build_icon_image()
        if image is None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Search files", lambda _icon, _item: self.callbacks.on_search()),
            pystray.MenuItem("Re-scan watched folder", lambda _icon, _item: self.callbacks.on_rescan()),
            pystray.MenuItem("Pause watching", lambda _icon, _item: self._toggle_pause()),
            pystray.MenuItem("Dry-run preview", lambda _icon, _item: self.callbacks.on_toggle_dry_run()),
            pystray.MenuItem("Undo last organization", lambda _icon, _item: self.callbacks.on_undo()),
            pystray.MenuItem("Settings", lambda _icon, _item: self.callbacks.on_settings()),
            pystray.MenuItem("Open data folder", lambda _icon, _item: self.callbacks.on_open_data_folder()),
            pystray.MenuItem("View log", lambda _icon, _item: self.callbacks.on_view_log()),
            pystray.MenuItem("Check for updates", lambda _icon, _item: self.callbacks.on_check_updates()),
            pystray.MenuItem("Reset all settings", lambda _icon, _item: self.callbacks.on_reset()),
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

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.callbacks.on_toggle_watcher()
