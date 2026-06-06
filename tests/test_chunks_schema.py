"""Verify v2 chunks and chunks_fts tables are created by initialize()."""

from __future__ import annotations

import unittest
from pathlib import Path

from golem.indexer import initialize, transaction


class TestChunksSchema(unittest.TestCase):
    def test_chunks_table_and_fts_are_created(self) -> None:
        db_path = Path(self._tmp()) / "test.db"
        with initialize(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                "AND name IN ('chunks','chunks_fts') ORDER BY name"
            ).fetchall()
            names = [r[0] for r in rows]
            self.assertEqual(names, ["chunks", "chunks_fts"])

    def test_chunks_triggers_are_created(self) -> None:
        db_path = Path(self._tmp()) / "test.db"
        with initialize(db_path) as conn:
            triggers = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('chunks_ai','chunks_ad','chunks_au')"
                ).fetchall()
            }
            self.assertEqual(triggers, {"chunks_ai", "chunks_ad", "chunks_au"})

    def test_chunks_fts_keeps_in_sync_via_triggers(self) -> None:
        db_path = Path(self._tmp()) / "test.db"
        with initialize(db_path) as conn:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO chunks(file_path, chunk_index, text, char_start, char_end) "
                    "VALUES ('/tmp/a.txt', 0, 'hello world', 0, 11)"
                )
                conn.execute(
                    "INSERT INTO chunks(file_path, chunk_index, text, char_start, char_end) "
                    "VALUES ('/tmp/a.txt', 1, 'second chunk', 12, 24)"
                )
            # Trigger should have populated the FTS index.
            rows = conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'hello'"
            ).fetchall()
            self.assertEqual(len(rows), 1)

            # DELETE should remove from the FTS index too.
            with transaction(conn):
                conn.execute("DELETE FROM chunks WHERE chunk_index = 0")
            rows = conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'hello'"
            ).fetchall()
            self.assertEqual(len(rows), 0)

    def _tmp(self) -> str:
        import tempfile

        return tempfile.mkdtemp()


if __name__ == "__main__":
    unittest.main()
