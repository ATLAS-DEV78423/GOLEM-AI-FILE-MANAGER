"""Tests for the system tray controller.

We cannot run a real pystray event loop in tests, so we test only the
parts that don't need a display: disable(), notify() on a missing icon,
and the callback wiring.
"""

from __future__ import annotations

import unittest

from golem.tray import TrayCallbacks, TrayController


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self) -> None:
        self.calls.append("called")


class TrayTests(unittest.TestCase):
    def test_disable_prevents_start(self) -> None:
        cbs = TrayCallbacks(
            on_search=_Recorder(),
            on_rescan=_Recorder(),
            on_toggle_dry_run=_Recorder(),
            on_undo=_Recorder(),
            on_settings=_Recorder(),
            on_quit=_Recorder(),
        )
        tray = TrayController(cbs)
        tray.disable()
        # Should be a no-op rather than crashing.
        tray.start()
        self.assertIsNone(tray._icon)

    def test_set_busy_does_not_crash_without_icon(self) -> None:
        cbs = TrayCallbacks(
            on_search=_Recorder(),
            on_rescan=_Recorder(),
            on_toggle_dry_run=_Recorder(),
            on_undo=_Recorder(),
            on_settings=_Recorder(),
            on_quit=_Recorder(),
        )
        tray = TrayController(cbs)
        tray.set_busy(True)
        tray.set_busy(False)
        tray.notify("Title", "Message")

    def test_toggle_pause_flips_internal_state_and_invokes_callback(self) -> None:
        called: list[bool] = []
        cbs = TrayCallbacks(
            on_search=_Recorder(),
            on_rescan=_Recorder(),
            on_toggle_dry_run=_Recorder(),
            on_undo=_Recorder(),
            on_settings=_Recorder(),
            on_toggle_watcher=lambda: called.append(tray._paused),
            on_quit=_Recorder(),
        )
        tray = TrayController(cbs)
        tray._toggle_pause()
        self.assertTrue(tray._paused)
        tray._toggle_pause()
        self.assertFalse(tray._paused)
        self.assertEqual(len(called), 2)


if __name__ == "__main__":
    unittest.main()
