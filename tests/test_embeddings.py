"""Tests for the embeddings module.

The sentence-transformers dependency is optional. When it is not
installed, the module returns zero vectors of the right shape; these
tests verify that contract. When the dependency IS installed, we do
not assert anything about vector *content* (which would be non-
deterministic), only that ``embed`` and ``embed_batch`` succeed.
"""

from __future__ import annotations

import unittest

from golem.embeddings import content_hash, dimension, embed, embed_batch, is_available


class TestEmbeddings(unittest.TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(is_available(), bool)

    def test_dimension_is_384(self) -> None:
        # all-MiniLM-L6-v2 outputs 384-dim vectors. This is also what
        # golem.vector_store._DIM expects; if you change one, change both.
        self.assertEqual(dimension(), 384)

    def test_embed_single_returns_list_of_correct_length(self) -> None:
        v = embed("hello world")
        self.assertIsInstance(v, list)
        self.assertEqual(len(v), 384)
        for x in v:
            self.assertIsInstance(x, float)

    def test_embed_batch_returns_one_vector_per_input(self) -> None:
        vs = embed_batch(["a", "b", "c"])
        self.assertEqual(len(vs), 3)
        for v in vs:
            self.assertEqual(len(v), 384)

    def test_embed_batch_empty(self) -> None:
        self.assertEqual(embed_batch([]), [])

    def test_zero_vector_when_model_unavailable(self) -> None:
        if is_available():
            self.skipTest("sentence-transformers installed; cannot test fallback path")
        v = embed("anything")
        self.assertEqual(
            sum(abs(x) for x in v),
            0.0,
            "without sentence-transformers, embed() should return a zero vector",
        )

    def test_content_hash_is_stable(self) -> None:
        h1 = content_hash("hello")
        h2 = content_hash("hello")
        self.assertEqual(h1, h2)
        h3 = content_hash("hello!")
        self.assertNotEqual(h1, h3)

    def test_content_hash_handles_empty_and_unicode(self) -> None:
        self.assertEqual(len(content_hash("")), 64)  # sha256 hex digest length
        self.assertEqual(len(content_hash("héllo wörld")), 64)


if __name__ == "__main__":
    unittest.main()
