"""Tests for the v2 chunks helpers in golem.indexer."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from golem.indexer import (
    get_chunk_count,
    get_chunks_for_path,
    initialize,
    insert_chunks,
    transaction,
)


def _make_chunk(idx: int, text: str, start: int = 0, end: int = 0):
    """Tiny stand-in for golem.chunker.Chunk that satisfies duck-typing."""
    from types import SimpleNamespace
    return SimpleNamespace(chunk_index=idx, text=text, char_start=start, char_end=end)


class TestChunksIndexer(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.db_path = self._tmp / "test.db"

    def test_insert_and_get_chunks(self) -> None:
        with initialize(self.db_path) as conn:
            chunks = [
                _make_chunk(0, "first", 0, 5),
                _make_chunk(1, "second", 6, 12),
                _make_chunk(2, "third", 13, 18),
            ]
            count = insert_chunks(conn, "/tmp/a.txt", chunks)
            self.assertEqual(count, 3)
            self.assertEqual(get_chunk_count(conn), 3)
            rows = get_chunks_for_path(conn, "/tmp/a.txt")
            self.assertEqual([r["chunk_index"] for r in rows], [0, 1, 2])
            self.assertEqual([r["text"] for r in rows], ["first", "second", "third"])

    def test_reinsert_replaces_existing_chunks(self) -> None:
        with initialize(self.db_path) as conn:
            insert_chunks(conn, "/tmp/a.txt", [_make_chunk(i, f"old{i}") for i in range(3)])
            new_chunks = [_make_chunk(i, f"new{i}") for i in range(5)]
            insert_chunks(conn, "/tmp/a.txt", new_chunks)
            self.assertEqual(get_chunk_count(conn), 5)
            rows = get_chunks_for_path(conn, "/tmp/a.txt")
            self.assertEqual([r["text"] for r in rows], [f"new{i}" for i in range(5)])

    def test_chunks_fts_stays_in_sync(self) -> None:
        with initialize(self.db_path) as conn:
            insert_chunks(
                conn,
                "/tmp/a.txt",
                [_make_chunk(0, "authentication is hard"), _make_chunk(1, "second chunk")],
            )
            # FTS5 trigger should have indexed both.
            fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
            self.assertEqual(fts_count, 2)
            hits = conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'authentication'"
            ).fetchall()
            self.assertEqual(len(hits), 1)


if __name__ == "__main__":
    unittest.main()
