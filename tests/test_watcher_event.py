"""Tests for the optional watchdog event watcher.

The watchdog dependency is optional. When it is not installed,
``is_available()`` returns False and ``start_event_watcher`` returns
None. These tests verify both paths.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from golem import watcher_events
from golem.watcher_events import is_available, start_event_watcher


class TestEventWatcher(unittest.TestCase):
    def test_module_imports_even_without_watchdog(self) -> None:
        # If the import succeeded, the module is at least structurally OK.
        self.assertIsNotNone(watcher_events)

    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(is_available(), bool)

    def test_start_returns_none_when_watchdog_missing(self) -> None:
        if is_available():
            self.skipTest("watchdog is installed; fallback path is untestable here")
        stop = threading.Event()
        out = start_event_watcher(Path(tempfile.gettempdir()), lambda p: None, stop)
        self.assertIsNone(out)

    def test_start_dispatches_stable_events_when_available(self) -> None:
        if not is_available():
            self.skipTest("watchdog not installed")
        with tempfile.TemporaryDirectory() as tmp:
            stop = threading.Event()
            seen: list[Path] = []
            t = start_event_watcher(Path(tmp), seen.append, stop)
            assert t is not None  # narrowed for mypy; we just checked availability
            observer_thread, pump_thread, _observer = t
            try:
                # Create a file, then wait for stability.
                target = Path(tmp) / "hello.txt"
                target.write_text("hi", encoding="utf-8")
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and not seen:
                    time.sleep(0.1)
                self.assertTrue(seen, "expected on_stable to fire for the new file")
                self.assertEqual(seen[0].name, "hello.txt")
            finally:
                # Stop the observer first, then drain the pump, so
                # neither thread is alive when TemporaryDirectory
                # tries to clean up.
                stop.set()
                observer_thread.join(timeout=2.0)
                pump_thread.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
