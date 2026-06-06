"""Tests for the hybrid FTS5 + vector RRF search."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from golem import hybrid_search
from golem.hybrid_search import HybridResult
from golem.indexer import initialize, insert_chunks


def _chunk(idx: int, text: str):
    from types import SimpleNamespace

    return SimpleNamespace(chunk_index=idx, text=text, char_start=0, char_end=len(text))


class TestHybridSearch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.db_path = self._tmp / "test.db"
        with initialize(self.db_path) as conn:
            # Two files, each with a couple of chunks.
            insert_chunks(
                conn,
                "/vault/notes/auth.md",
                [
                    _chunk(0, "authentication and authorization patterns"),
                    _chunk(1, "session token handling"),
                ],
            )
            insert_chunks(
                conn,
                "/vault/notes/billing.md",
                [
                    _chunk(0, "invoice numbers and payment terms"),
                    _chunk(1, "tax compliance procedures"),
                ],
            )

    def test_empty_query_returns_empty(self) -> None:
        with initialize(self.db_path) as conn:
            self.assertEqual(hybrid_search.search(conn, ""), [])
            self.assertEqual(hybrid_search.search(conn, "   "), [])

    def test_keyword_match_uses_fts(self) -> None:
        with initialize(self.db_path) as conn:
            results = hybrid_search.search(conn, "authentication", top_k=5)
            self.assertGreater(len(results), 0)
            # Without sqlite-vec + sentence-transformers installed, we
            # can only verify the keyword match.
            auth_hits = [r for r in results if "auth.md" in r.file_path]
            self.assertGreater(len(auth_hits), 0)
            self.assertEqual(auth_hits[0].match_type, "keyword")

    def test_token_sanitization_skips_short_tokens(self) -> None:
        with initialize(self.db_path) as conn:
            # "a" is too short; the sanitizer drops it. Result must be
            # empty (no FTS query that matches anything).
            self.assertEqual(hybrid_search.search(conn, "a b c"), [])

    def test_rrf_fuses_both_sources(self) -> None:
        with initialize(self.db_path) as conn:
            # Stub vector_store.search to return a hit.
            fake_vec = [
                {
                    "file_path": "/vault/notes/billing.md",
                    "text": "invoice numbers and payment terms",
                    "score": 0.1,
                }
            ]
            with (
                patch("golem.vector_store.is_available", return_value=True),
                patch("golem.vector_store.search", return_value=fake_vec),
            ):
                results = hybrid_search.search(conn, "invoice", top_k=5)
            self.assertGreater(len(results), 0)
            types = {r.match_type for r in results}
            self.assertIn("both", types, f"expected 'both' match in {types}")
            # The top result must be a 'both' match.
            self.assertEqual(results[0].match_type, "both")
            self.assertGreater(results[0].rrf_score, 0.0)

    def test_dedupe_by_file_path(self) -> None:
        with initialize(self.db_path) as conn:
            results = hybrid_search.search(conn, "authentication OR token", top_k=10)
            paths = [r.file_path for r in results]
            # No duplicate file_path in the output.
            self.assertEqual(len(paths), len(set(paths)))

    def test_hybrid_result_to_dict(self) -> None:
        hr = HybridResult(
            file_path="/x",
            chunk_text="hi",
            rrf_score=0.1,
            bm25_score=-1.0,
            vector_score=0.05,
            match_type="both",
        )
        d = hr.to_dict()
        self.assertEqual(d["file_path"], "/x")
        self.assertEqual(d["match_type"], "both")
        self.assertEqual(d["rrf_score"], 0.1)


if __name__ == "__main__":
    unittest.main()
