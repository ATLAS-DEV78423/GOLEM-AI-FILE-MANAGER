"""Tests for the undo path (golem.undo.undo_last).

The undo path is critical: it reverses a real on-disk move. If it
fails, the user loses a file in some other folder. We exercise the
happy path, the "no undoable action" path, and the "target is
already gone" path. The cross-volume case (safe_move) is covered
implicitly by the safe_move tests.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from golem.indexer import (
    FileRecord,
    add_undo_log,
    initialize,
    transaction,
    upsert_file,
)
from golem.undo import undo_last
from golem.vault_writer import note_path_for, write_note


def _seed(conn, source: Path, target: Path) -> int:
    """Insert a file row + an undo log row mimicking a successful move.

    The size is read from whichever side of the move actually exists
    on disk — usually ``target`` because the file has been moved there
    and the source has been deleted. Uses a single transaction.
    """
    size_path = target if target.exists() else source
    try:
        size_bytes = size_path.stat().st_size
    except OSError:
        size_bytes = 0
    with transaction(conn):
        file_id = upsert_file(
            conn,
            FileRecord(
                original_filename=source.name,
                clean_filename=source.stem,
                original_path=str(source),
                current_path=str(target),
                file_type=source.suffix.lstrip("."),
                size_kb=size_bytes / 1024.0,
                content_hash="hash:1",
                duplicate_of=None,
                extracted_text="",
                summary="",
                tags="",
                key_contents="",
                category="Other",
                obsidian_note_path="",
                date_indexed="2026-06-03T00:00:00Z",
                last_modified="2026-06-03T00:00:00Z",
                index_status="done",
            ),
        )
        add_undo_log(conn, "move", file_id, str(source), str(target), "2026-06-03T00:00:00Z")
    return file_id


class UndoLastTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "golem.db"
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.source_dir = self.tmp / "watched"
        self.source_dir.mkdir()
        self.conn = initialize(self.db)

    def tearDown(self) -> None:
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_undoable_action_returns_empty(self) -> None:
        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "empty")

    def test_undo_restores_source_and_marks_reversed(self) -> None:
        source = self.source_dir / "report.txt"
        source.write_text("budget", encoding="utf-8")
        target = self.vault / "GOLEM Files" / "Other" / "report.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("budget", encoding="utf-8")
        # Remove the source so the move is "real".
        source.unlink()

        _seed(self.conn, source, target)

        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(source.exists(), "source was not restored")
        self.assertFalse(target.exists(), "target was not removed")
        # current_path should now match the original (from_path).
        row = self.conn.execute("SELECT current_path, original_path FROM files WHERE id = 1").fetchone()
        self.assertEqual(row["current_path"], str(source))
        # The undo log row is marked reversed.
        flag = self.conn.execute("SELECT reversed FROM undo_log").fetchone()["reversed"]
        self.assertEqual(flag, 1)

    def test_undo_when_target_already_missing_marks_reversed(self) -> None:
        source = self.source_dir / "ghost.txt"
        target = self.vault / "GOLEM Files" / "Other" / "ghost.txt"
        # No target file — the user already deleted it manually.
        _seed(self.conn, source, target)
        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "missing")
        flag = self.conn.execute("SELECT reversed FROM undo_log").fetchone()["reversed"]
        self.assertEqual(flag, 1)

    def test_undo_deletes_unedited_note(self) -> None:
        source = self.source_dir / "doc.txt"
        target = self.vault / "GOLEM Files" / "Other" / "doc.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        source.unlink(missing_ok=True)
        file_id = _seed(self.conn, source, target)

        # Write a non-user-edited note and link it.
        note_path = note_path_for(self.vault, "doc")
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("---\nuser_edited: false\n---\n", encoding="utf-8")
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE files SET obsidian_note_path = ? WHERE id = ?",
                (str(note_path), file_id),
            )

        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(note_path.exists(), "unedited note was not removed")

    def test_undo_preserves_user_edited_note(self) -> None:
        source = self.source_dir / "edited.txt"
        target = self.vault / "GOLEM Files" / "Other" / "edited.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        source.unlink(missing_ok=True)
        file_id = _seed(self.conn, source, target)

        note_path = note_path_for(self.vault, "edited")
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("---\nuser_edited: true\n---\n", encoding="utf-8")
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE files SET obsidian_note_path = ? WHERE id = ?",
                (str(note_path), file_id),
            )

        result = undo_last(self.conn, self.vault)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(note_path.exists(), "user-edited note was wrongly deleted")


if __name__ == "__main__":
    unittest.main()
