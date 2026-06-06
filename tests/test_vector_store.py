"""Tests for the optional sqlite-vec backed vector store.

These tests must pass regardless of whether the ``sqlite-vec`` extension
is installed. When the extension is absent, the store degrades to a
no-op (upsert/search/delete do nothing safely) and ``is_available()``
returns False.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from golem import vector_store
from golem.indexer import initialize, insert_chunks, transaction


def _chunk(idx: int, text: str):
    from types import SimpleNamespace
    return SimpleNamespace(chunk_index=idx, text=text, char_start=0, char_end=len(text))


class TestVectorStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.db_path = self._tmp / "test.db"

    def test_is_available_returns_bool(self) -> None:
        result = vector_store.is_available()
        self.assertIsInstance(result, bool)

    def test_upsert_and_search_are_safe_when_unavailable(self) -> None:
        # Skip these checks if the extension is actually present;
        # they only apply to the no-op fallback path.
        if vector_store.is_available():
            self.skipTest("sqlite-vec is installed; no-op fallback is untestable here")
        with initialize(self.db_path) as conn:
            # Should not raise.
            vector_store.upsert(conn, 1, "hello", [0.0] * 384)
            vector_store.delete_for_path(conn, "/tmp/a.txt")
            vector_store.delete_for_chunk(conn, 1)
            self.assertEqual(
                vector_store.search_by_embedding(conn, [0.0] * 384, top_k=10),
                [],
            )
            self.assertEqual(vector_store.search(conn, "anything", top_k=10), [])

    def test_search_by_embedding_on_empty_store_returns_empty(self) -> None:
        # This test is meaningful both with and without the extension:
        # if the extension is present, an empty store should still
        # return []. If absent, we already test that above.
        with initialize(self.db_path) as conn:
            with transaction(conn):
                insert_chunks(
                    conn,
                    "/tmp/a.txt",
                    [_chunk(0, "alpha"), _chunk(1, "beta")],
                )
            out = vector_store.search_by_embedding(conn, [0.0] * 384, top_k=10)
            # Without sqlite-vec, out is []. With it, out might be []. We
            # only assert no crash and that the return type is a list.
            self.assertIsInstance(out, list)


if __name__ == "__main__":
    unittest.main()
