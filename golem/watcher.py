from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from .constants import SYSTEM_SKIP_DIRS
from .utils import is_hidden_or_system_dir


class PollingWatcher:
    def __init__(self, folder: Path, on_new_file: Callable[[Path], None], interval: float = 3.0):
        self.folder = folder
        self.on_new_file = on_new_file
        self.interval = interval
        self._stop = threading.Event()
        self._known: dict[str, float] = {}

    def start(self) -> threading.Thread:
        self._snapshot_known()
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()

    def _snapshot_known(self) -> None:
        self._known.clear()
        for path in self.folder.rglob("*"):
            if not self._should_track(path):
                continue
            try:
                self._known[str(path)] = path.stat().st_mtime
            except Exception:
                continue

    def _should_track(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if any(is_hidden_or_system_dir(part) or part in SYSTEM_SKIP_DIRS for part in path.parts):
            return False
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                for path in self.folder.rglob("*"):
                    if not self._should_track(path):
                        continue
                    key = str(path)
                    mtime = path.stat().st_mtime
                    previous = self._known.get(key)
                    if previous is None:
                        self._known[key] = mtime
                        self.on_new_file(path)
                        continue
                    if mtime > previous:
                        self._known[key] = mtime
                        self.on_new_file(path)
                time.sleep(self.interval)
            except Exception:
                time.sleep(self.interval)
