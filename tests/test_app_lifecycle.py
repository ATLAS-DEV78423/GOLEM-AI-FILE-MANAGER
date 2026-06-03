"""Integration tests for GolemApplication.

These tests avoid a real Tk root by patching the Tk-touching pieces
(``DesktopApp``) with a stub. The non-UI methods (``_reset_all``,
``_search``, ``_open_path``, etc.) are exercised against a real
SQLite database in a temp dir.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from golem.config import AppConfig
from golem.indexer import (
    FileRecord,
    connect,
    initialize,
    save_settings,
    transaction,
    upsert_file,
)
from golem.summarizer import HeuristicSummarizer


class _StubDesktopApp:
    """Stand-in for ``DesktopApp`` that records method calls but does not touch Tk.

    We replace the real ``DesktopApp`` for the duration of the test so
    ``GolemApplication.__init__`` does not try to create a Tk root. The
    ``_reset_all`` path calls ``ui.show_onboarding()``; we just record that.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # ``GolemApplication`` passes 4 callbacks; we accept any positional
        # args and ignore them. The real ``DesktopApp`` builds a Tk root;
        # we don't need one here.
        self.shown_onboarding = False
        self.status_messages: list[str] = []
        # ``GolemApplication.__init__`` schedules three ``after`` calls
        # against ``self.ui.root``; provide a no-op root that swallows
        # them so the constructor can complete without Tk.
        self.root = _StubTkRoot()

    def show_onboarding(self) -> None:
        self.shown_onboarding = True

    def show_popup(self) -> None:
        pass

    def set_status(self, message: str) -> None:
        self.status_messages.append(message)

    def run(self) -> None:
        pass


class _StubTkRoot:
    def after(self, _ms: int, _fn: Any) -> None:
        return None


class _StubTray:
    """Stand-in for ``TrayController``. Records notifications."""

    def __init__(self, callbacks: Any = None) -> None:
        self.callbacks = callbacks
        self.busy = False
        self.disabled = False
        self.notifications: list[tuple[str, str]] = []
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def disable(self) -> None:
        self.disabled = True

    def set_busy(self, busy: bool) -> None:
        self.busy = busy

    def notify(self, title: str, message: str) -> None:
        self.notifications.append((title, message))


class _StubPollingWatcher:
    instances: list["_StubPollingWatcher"] = []

    def __init__(self, folder: Path, on_new_file: Any) -> None:
        self.folder = folder
        self.on_new_file = on_new_file
        self.stopped = False
        _StubPollingWatcher.instances.append(self)

    def start(self) -> tuple[Any, Any]:
        return (None, None)

    def stop(self) -> None:
        self.stopped = True


def _seed_db(db_path: Path) -> None:
    """Populate the DB with one settings row, one file row, and one undo row."""
    conn = initialize(db_path)
    with transaction(conn):
        upsert_file(
            conn,
            FileRecord(
                original_filename="seed.txt",
                clean_filename="Seed",
                original_path="C:/tmp/seed.txt",
                current_path="C:/tmp/seed.txt",
                file_type="txt",
                size_kb=1.0,
                content_hash="seedhash:1",
                duplicate_of=None,
                extracted_text="seed",
                summary="seed summary",
                tags="seed",
                key_contents="seed",
                category="Other",
                obsidian_note_path="",
                date_indexed="2026-05-31T00:00:00Z",
                last_modified="2026-05-31T00:00:00Z",
                index_status="done",
            ),
        )
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?)",
            ("watched_folder", "C:/tmp/seed.txt"),
        )
        conn.execute(
            "INSERT INTO undo_log(action, file_id, from_path, to_path, timestamp, reversed) "
            "VALUES(?, ?, ?, ?, ?, 0)",
            ("move", 1, "C:/tmp/seed.txt", "C:/tmp/seed-done.txt", "2026-05-31T00:00:00Z"),
        )
    conn.close()


class ResetAllTests(unittest.TestCase):
    """Regression test for the bug where ``_reset_all`` referenced the
    unimported ``transaction`` symbol and raised ``NameError`` the first
    time the user clicked "Reset all settings" from the tray.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "golem.db"
        _seed_db(self.db_path)

    def test_reset_all_wipes_settings_files_and_undo_log(self) -> None:
        # Confirm pre-conditions.
        with closing(connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM settings").fetchone()["c"],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM undo_log").fetchone()["c"],
                1,
            )

        # Build the application with the UI pieces stubbed.
        with patch("golem.app.DesktopApp", _StubDesktopApp), patch(
            "golem.app.TrayController", _StubTray
        ), patch("golem.app.PollingWatcher", _StubPollingWatcher):
            from golem.app import GolemApplication

            data_dir = self.tmp / "data"
            data_dir.mkdir()
            with patch("golem.app.default_data_dir", return_value=data_dir), patch(
                "golem.app.ensure_db_file", return_value=self.db_path
            ):
                app = GolemApplication()
                try:
                    app._reset_all()
                finally:
                    app.shutdown()

        # Post-conditions: every table that _reset_all touches is empty.
        with closing(connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"],
                0,
                "files table should be empty after reset",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM files_fts").fetchone()["c"],
                0,
                "files_fts should be empty after reset (trigger fires on DELETE)",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM settings").fetchone()["c"],
                0,
                "settings table should be empty after reset",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM undo_log").fetchone()["c"],
                0,
                "undo_log should be empty after reset",
            )

    def test_reset_all_triggers_onboarding(self) -> None:
        """After a reset the UI must show onboarding so the user can re-enter config."""
        stub_ui = _StubDesktopApp()
        with patch("golem.app.DesktopApp", return_value=stub_ui), patch(
            "golem.app.TrayController", _StubTray
        ), patch("golem.app.PollingWatcher", _StubPollingWatcher):
            from golem.app import GolemApplication

            data_dir = self.tmp / "data"
            data_dir.mkdir()
            with patch("golem.app.default_data_dir", return_value=data_dir), patch(
                "golem.app.ensure_db_file", return_value=self.db_path
            ):
                app = GolemApplication()
                try:
                    self.assertFalse(stub_ui.shown_onboarding)
                    app._reset_all()
                    self.assertTrue(stub_ui.shown_onboarding)
                finally:
                    app.shutdown()


class StatusBarTests(unittest.TestCase):
    """Regression tests for the status-bar priority logic.

    Background threads post to ``error_queue`` and ``progress_queue``.
    The error pump owns the status bar for a few seconds; the progress
    pump must NOT clobber the error during that window.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "golem.db"
        initialize(self.db_path).close()

    def _make_app(self) -> Any:
        with patch("golem.app.DesktopApp", _StubDesktopApp), patch(
            "golem.app.TrayController", _StubTray
        ), patch("golem.app.PollingWatcher", _StubPollingWatcher):
            from golem.app import GolemApplication

            data_dir = self.tmp / "data"
            data_dir.mkdir()
            with patch("golem.app.default_data_dir", return_value=data_dir), patch(
                "golem.app.ensure_db_file", return_value=self.db_path
            ):
                app = GolemApplication()
                self.addCleanup(app.shutdown)
                return app

    def test_error_message_is_not_clobbered_by_immediate_progress(self) -> None:
        app = self._make_app()
        # An error arrives.
        app.error_queue.put_nowait("Cannot read vault/Finance/report.pdf: permission denied")
        # The pump runs once and posts the error.
        app._pump_errors()
        self.assertTrue(app.ui.status_messages)
        self.assertIn("permission denied", app.ui.status_messages[-1])
        # Immediately, a progress tick arrives and the pump runs.
        app.progress_queue.put_nowait({"current_file": "next.txt", "progress": 0.5})
        app._pump_progress()
        # The progress pump must not have overwritten the error.
        self.assertIn("permission denied", app.ui.status_messages[-1])

    def test_progress_after_error_window_replaces_status(self) -> None:
        import golem.app as app_mod
        import time as time_mod

        app = self._make_app()
        # An error arrives and the error window is opened.
        app.error_queue.put_nowait("boom")
        app._pump_errors()
        # Force the error window to expire.
        app._status_error_until = time_mod.monotonic() - 1.0
        # A progress tick now should win.
        app.progress_queue.put_nowait({"current_file": "x.txt", "progress": 0.1})
        app._pump_progress()
        # The last status is a progress line, not the error.
        self.assertIn("x.txt", app.ui.status_messages[-1])


if __name__ == "__main__":
    unittest.main()
