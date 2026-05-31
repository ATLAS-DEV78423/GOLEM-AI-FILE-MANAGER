from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


def _build_icon_image(color: str = "#b87333"):
    try:
        from PIL import Image, ImageDraw  # type: ignore

        image = Image.new("RGBA", (64, 64), (15, 15, 15, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill=color)
        draw.ellipse((22, 22, 42, 42), fill=(15, 15, 15, 255))
        return image
    except Exception:
        return None


@dataclass
class TrayCallbacks:
    on_search: Callable[[], None]
    on_rescan: Callable[[], None]
    on_toggle_dry_run: Callable[[], None]
    on_undo: Callable[[], None]
    on_settings: Callable[[], None]
    on_quit: Callable[[], None]


class TrayController:
    def __init__(self, callbacks: TrayCallbacks):
        self.callbacks = callbacks
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import pystray  # type: ignore
        except Exception:
            return

        image = _build_icon_image()
        if image is None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Search files", lambda _icon, _item: self.callbacks.on_search()),
            pystray.MenuItem("Re-scan watched folder", lambda _icon, _item: self.callbacks.on_rescan()),
            pystray.MenuItem("Dry-run preview", lambda _icon, _item: self.callbacks.on_toggle_dry_run()),
            pystray.MenuItem("Undo last organisation", lambda _icon, _item: self.callbacks.on_undo()),
            pystray.MenuItem("Settings", lambda _icon, _item: self.callbacks.on_settings()),
            pystray.MenuItem("Quit", lambda _icon, _item: self.callbacks.on_quit()),
        )
        self._icon = pystray.Icon("GOLEM", image, "GOLEM", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

