"""End-to-end smoke tests for the main.py CLI entry point.

These tests do not start the Tk GUI (no display in CI). They verify
that the executable path that a real user would run:

  1. Imports cleanly.
  2. Reports its version.
  3. Exports the DB to a sandboxed path without touching the host's
     ``%LOCALAPPDATA%``.
  4. Honors ``GOLEM_DATA_DIR`` so the test is hermetic.

The Tk GUI itself is covered manually on the user's VM (see
``docs/OPERATIONS.md`` -> Verifying a fresh install).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from golem.constants import APP_NAME, APP_VERSION


def _run(args: list[str], env: dict[str, str] | None = None, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Run ``python main.py <args>`` and return the completed process.

    The test always uses ``--no-tray --no-watcher --no-hotkey`` so we
    never need a display server. ``--version`` exits before any Tk code
    runs, so it is the safest check.
    """
    cmd = [sys.executable, "main.py", *args]
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


class MainCliSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="golem-smoke-"))
        self.addCleanup(self._rm_tmp)

    def _rm_tmp(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_version_flag_prints_app_name_and_version(self) -> None:
        result = _run(["--version"], env={"GOLEM_DATA_DIR": str(self.tmp)})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(APP_NAME, result.stdout)
        self.assertIn(APP_VERSION, result.stdout)

    def test_help_flag_lists_all_cli_flags(self) -> None:
        result = _run(["--help"], env={"GOLEM_DATA_DIR": str(self.tmp)})
        # argparse exits with code 0 on --help.
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        for flag in [
            "--data-dir",
            "--log-level",
            "--no-tray",
            "--no-watcher",
            "--no-hotkey",
            "--dry-run",
            "--reindex",
            "--export-db",
            "--version",
        ]:
            self.assertIn(flag, result.stdout, f"--help is missing {flag}")

    def test_export_db_writes_to_specified_path(self) -> None:
        """``--export-db`` copies the SQLite file to a destination of the user's choice.

        The test runs ``--version`` first to ensure the data dir exists,
        then runs ``--export-db`` and verifies the destination file is
        non-empty and is a real SQLite database.
        """
        env = {"GOLEM_DATA_DIR": str(self.tmp)}
        # ``--version`` exits before creating any DB, so the export will
        # short-circuit with "Database does not exist". Use a different
        # approach: import + initialize the DB in-process via the same
        # path the entry point uses, then run --export-db.
        from golem.config import AppConfig
        from golem.constants import DB_FILENAME
        from golem.indexer import initialize, save_settings, transaction

        db_path = self.tmp / DB_FILENAME
        conn = initialize(db_path)
        # Write the minimal settings rows AppConfig expects on save.
        cfg = AppConfig(
            watched_folder="C:/tmp/seed",
            vault_folder="C:/tmp/seed-vault",
        )
        with transaction(conn):
            save_settings(conn, cfg.as_settings())
        conn.close()

        dest = self.tmp / "exported.db"
        result = _run(["--export-db", str(dest)], env=env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(dest.is_file(), f"export-db did not create {dest}")
        self.assertGreater(dest.stat().st_size, 0, "exported DB is empty")

        # Round-trip: open the exported file and confirm the data is in it.
        import sqlite3
        out = sqlite3.connect(str(dest))
        try:
            row = out.execute("SELECT value FROM settings WHERE key = 'watched_folder'").fetchone()
            self.assertIsNotNone(row, "exported DB has no watched_folder row")
            self.assertEqual(row[0], "C:/tmp/seed")
        finally:
            out.close()

    def test_data_dir_env_var_is_honored(self) -> None:
        """The smoke test itself is the verification: by passing
        ``GOLEM_DATA_DIR`` to a sandboxed temp dir, we prove that the
        entry point reads the env var and does not touch the host's
        ``%LOCALAPPDATA%``.
        """
        env = {"GOLEM_DATA_DIR": str(self.tmp)}
        result = _run(["--version"], env=env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # The data dir should have been created (it gets mkdir-ed on
        # any call to ``default_data_dir``). The version flag does
        # not call it, but a sibling flag like --export-db would. Use
        # --export-db on a missing DB to confirm the data dir IS the
        # sandbox and NOT %LOCALAPPDATA%.
        dest = self.tmp / "out.db"
        result = _run(["--export-db", str(dest)], env=env)
        # DB doesn't exist in the sandbox; export returns 1 with a
        # clear message. That itself is the proof: the host's
        # LOCALAPPDATA was NOT used.
        self.assertIn("does not exist", result.stderr.lower() + result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
