"""Full-pipeline integration tests for GOLEM.

Exercises the complete user flow:
  1. Initialize the DB and config
  2. Scan a folder (index files, organize into vault, create notes)
  3. Search for indexed files
  4. Undo the last organization
  5. Verify crash marker lifecycle
  6. Verify DB backup rotation
"""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

from golem.config import AppConfig
from golem.indexer import (
    backup_database,
    check_integrity,
    checkpoint_wal,
    connect,
    get_settings,
    initialize,
    optimize_fts,
    restore_from_backup,
    save_settings,
    search_files,
)
from golem.scanner import scan_folder
from golem.summarizer import HeuristicSummarizer
from golem.undo import undo_last


class FullPipelineTests(unittest.TestCase):
    """End-to-end integration tests that exercise the core loop."""

    def setUp(self) -> None:
        self.sandbox = Path(tempfile.mkdtemp())
        self.watched = self.sandbox / "watched"
        self.vault = self.sandbox / "vault"
        self.watched.mkdir()
        self.vault.mkdir()
        self.db_path = self.sandbox / "golem.db"
        self.conn = initialize(self.db_path)

    def tearDown(self) -> None:
        try:
            if self.conn is not None:
                checkpoint_wal(self.conn, "TRUNCATE")
                self.conn.close()
        except Exception:
            pass
        import shutil

        shutil.rmtree(self.sandbox, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helper: create a file in the watched folder
    # ------------------------------------------------------------------

    def _write(self, name: str, content: str) -> Path:
        p = self.watched / name
        p.write_text(content, encoding="utf-8")
        return p

    def _search(self, query: str) -> list[dict]:
        return search_files(self.conn, query)

    # ------------------------------------------------------------------
    # 1. Scan → index → organize full pipeline
    # ------------------------------------------------------------------

    def test_full_scan_indexes_and_organizes_files(self) -> None:
        """Scan a folder with multiple text files, verify they get indexed,
        organized into categories, and Obsidian notes are created."""
        # Seed the watched folder - use only .txt files since .pdf
        # cannot be extracted (the extractor rejects binary/non-text).
        self._write("budget_q1.txt", "budget report for Q1 2026 invoice payment")
        self._write("research_notes.txt", "study on machine learning methods and datasets")

        # Run the scan
        result = scan_folder(
            self.conn,
            self.watched,
            self.vault,
            HeuristicSummarizer(),
            log=lambda msg: None,
            dry_run=False,
        )
        self.assertEqual(result.processed, 2)
        self.assertEqual(result.errors, 0)

        # Verify files were moved into vault/GOLEM Files/<category>/
        self.assertTrue((self.vault / "GOLEM Files").exists())
        # Check that the original files are no longer in watched
        self.assertFalse((self.watched / "budget_q1.txt").exists())
        self.assertFalse((self.watched / "research_notes.txt").exists())

        # Verify Obsidian notes were created
        self.assertTrue((self.vault / "GOLEM").exists())
        note_count = len(list((self.vault / "GOLEM").glob("*.md")))
        self.assertGreaterEqual(note_count, 1)

        # Verify FTS index
        rows = self.conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()
        self.assertEqual(rows["c"], 2)
        rows = self.conn.execute("SELECT COUNT(*) AS c FROM files_fts").fetchone()
        self.assertEqual(rows["c"], 2)

    def test_scan_with_dry_run_does_not_move_files(self) -> None:
        """In dry-run mode, files must be indexed but NOT moved."""
        self._write("test.txt", "dry run test content")
        result = scan_folder(
            self.conn,
            self.watched,
            self.vault,
            HeuristicSummarizer(),
            dry_run=True,
        )
        self.assertEqual(result.processed, 1)
        # File should still be in watched
        self.assertTrue((self.watched / "test.txt").exists())
        # Should not be in vault yet
        self.assertFalse((self.vault / "GOLEM Files").exists())

    def test_search_after_scan_returns_results(self) -> None:
        """After scanning, search must find indexed content.

        FTS5 tokenises on word boundaries, so we search for a term that
        appears in the file text AND that gets indexed into the FTS
        columns (summary, tags, key_contents, category).
        """
        self._write("report_march.txt", "march financial report with budget details")
        self._write("notes_march.txt", "personal journal entry for march")
        scan_folder(
            self.conn,
            self.watched,
            self.vault,
            HeuristicSummarizer(),
            log=lambda msg: None,
        )
        # The category and summary should contain financial/march terms
        results = self._search("march")
        self.assertGreaterEqual(len(results), 1, "Expected at least 1 result for 'march'")
        # Verify at least one result has a clean_filename that includes 'March'
        # (the summarizer capitalises the first letter of the clean filename)
        found = any(
            "March" in (r.get("clean_filename") or "")
            or "march" in (r.get("summary") or "").lower()
            for r in results
        )
        self.assertTrue(found, f"No result matched 'march': {results}")

    # ------------------------------------------------------------------
    # 2. Undo flow
    # ------------------------------------------------------------------

    def test_undo_reverses_file_move(self) -> None:
        """Undo last must move the file back to its original location."""
        self._write("undo_test.txt", "content for undo test")
        scan_folder(
            self.conn,
            self.watched,
            self.vault,
            HeuristicSummarizer(),
            log=lambda msg: None,
        )
        # Verify it was moved
        self.assertFalse((self.watched / "undo_test.txt").exists())

        # Undo
        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "ok")
        self.assertIn("Restored", result["message"])

        # File should be back
        self.assertTrue((self.watched / "undo_test.txt").exists())

    def test_undo_with_occupied_target_uses_unique_path(self) -> None:
        """If the original location is now occupied, undo must use a unique path."""
        self._write("collision.txt", "original content")
        scan_folder(
            self.conn,
            self.watched,
            self.vault,
            HeuristicSummarizer(),
            log=lambda msg: None,
        )
        # Recreate the file at the original location
        self._write("collision.txt", "new content that blocks undo")

        # Undo should still work but restore to a unique path
        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "ok")
        self.assertIn("Restored to", result["message"])

    # ------------------------------------------------------------------
    # 3. DB health and maintenance
    # ------------------------------------------------------------------

    def test_integrity_check_passes_on_healthy_db(self) -> None:
        ok, msg = check_integrity(self.conn)
        self.assertTrue(ok, f"Integrity check failed: {msg}")

    def test_backup_rotation_creates_files(self) -> None:
        """Backing up the DB must create .backup.1 file."""
        # Checkpoint WAL so the main file is fully consistent
        checkpoint_wal(self.conn, "TRUNCATE")
        backup_database(self.sandbox, max_backups=3)
        b1 = self.sandbox / "golem.db.backup.1"
        self.assertTrue(b1.exists(), "Backup file was not created")

    def test_backup_rotation_creates_multiple_generations(self) -> None:
        """Calling backup multiple times must rotate backups."""
        for _ in range(4):
            checkpoint_wal(self.conn, "TRUNCATE")
            backup_database(self.sandbox, max_backups=3)
        # We should have .backup.1, .backup.2, .backup.3
        for i in range(1, 4):
            self.assertTrue(
                (self.sandbox / f"golem.db.backup.{i}").exists(),
                f"Backup generation {i} missing",
            )

    def test_restore_from_backup_recovers_data(self) -> None:
        """Restoring from backup must recover the database state."""
        checkpoint_wal(self.conn, "TRUNCATE")
        backup_database(self.sandbox, max_backups=3)
        # Corrupt the original by deleting a table
        self.conn.execute("DROP TABLE IF EXISTS files")
        self.conn.commit()
        # Checkpoint and close so the main file reflects the dropped table
        checkpoint_wal(self.conn, "TRUNCATE")
        self.conn.close()
        self.conn = None  # prevent double-close in tearDown

        # Restore from backup
        restored = restore_from_backup(self.sandbox)
        self.assertTrue(restored, "Restore reported failure")

        # Verify the files table is back
        with closing(connect(self.db_path)) as conn2:
            tables = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = {t["name"] for t in tables}
            self.assertIn("files", names)

    def test_wal_checkpoint_does_not_crash(self) -> None:
        checkpoint_wal(self.conn, "PASSIVE")
        checkpoint_wal(self.conn, "TRUNCATE")
        # If we get here without error, it worked

    def test_fts_optimize_does_not_crash(self) -> None:
        optimize_fts(self.conn)
        # If we get here without error, it worked

    # ------------------------------------------------------------------
    # 4. Crash marker lifecycle
    # ------------------------------------------------------------------

    def test_crash_marker_tracking(self) -> None:
        """The crash marker must be created on init and cleared on shutdown."""
        from golem.app import GolemApplication

        data_dir = self.sandbox / "crash-test-data"
        data_dir.mkdir()
        marker = data_dir / ".golem_running"

        class _StubUI:
            def __init__(self, *a, **kw):
                self.root = _StubRoot()

            def show_onboarding(self):
                pass

            def show_popup(self):
                pass

            def set_status(self, m):
                pass

            def run(self):
                pass

        class _StubRoot:
            def after(self, ms, fn):
                return None

        class _StubTray2:
            def __init__(self, callbacks=None):
                self.callbacks = callbacks or MagicMock()
                self.callbacks.dry_run = False
                self.callbacks.paused = False
                self.callbacks.autostart_enabled = False

            def start(self):
                pass

            def stop(self):
                pass

            def disable(self):
                pass

            def set_busy(self, b):
                pass

            def notify(self, t, m):
                pass

            def set_paused_icon(self, p):
                pass

        with (
            patch("golem.app.DesktopApp", _StubUI),
            patch("golem.app.TrayController", _StubTray2),
            patch("golem.app.PollingWatcher", MagicMock),
            patch("golem.app.default_data_dir", return_value=data_dir),
            patch("golem.app.ensure_db_file", return_value=self.db_path),
        ):
            app = GolemApplication()
            # Marker should exist after init
            self.assertTrue(marker.exists(), "Crash marker not created on init")
            app.shutdown()
            # Marker should be removed after shutdown
            self.assertFalse(marker.exists(), "Crash marker not removed on shutdown")

    # ------------------------------------------------------------------
    # 5. Config persistence round-trip
    # ------------------------------------------------------------------

    def test_config_save_and_load_round_trip(self) -> None:
        """Saving config then reloading must produce identical values."""
        original = AppConfig(
            watched_folder="C:/test/watched",
            vault_folder="C:/test/vault",
            llm_provider="openai",
            llm_api_key="sk-test-key-12345",
            llm_model="gpt-4",
            llm_base_url="https://api.openai.com/v1",
            dry_run=True,
            watch_enabled=False,
            confidence_threshold=0.75,
            terms_accepted=True,
            terms_version="1.0",
            autostart_enabled=True,
        )
        save_settings(self.conn, original.as_settings())
        self.conn.commit()

        loaded = AppConfig.from_settings(get_settings(self.conn))
        for attr in [
            "watched_folder",
            "vault_folder",
            "llm_provider",
            "llm_api_key",
            "llm_model",
            "llm_base_url",
            "dry_run",
            "watch_enabled",
            "confidence_threshold",
            "terms_accepted",
            "terms_version",
            "autostart_enabled",
        ]:
            self.assertEqual(
                getattr(original, attr),
                getattr(loaded, attr),
                f"Mismatch for config attribute {attr}",
            )


if __name__ == "__main__":
    unittest.main()
