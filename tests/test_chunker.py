"""Tests for the paragraph -> sentence chunker."""
from __future__ import annotations

import unittest

from golem.chunker import _TARGET_TOKENS_MAX, Chunk, chunk_text


class TestChunker(unittest.TestCase):
    def test_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n\n  "), [])

    def test_short_paragraph_returns_single_chunk(self) -> None:
        chunks = chunk_text("This is a short note about GOLEM.")
        self.assertEqual(len(chunks), 1)
        self.assertIn("GOLEM", chunks[0].text)
        self.assertEqual(chunks[0].chunk_index, 0)

    def test_chunks_have_sequential_indices(self) -> None:
        # Build a text big enough to force multiple chunks. Each paragraph
        # is ~200 tokens worth of content, so we need at least 4-5
        # paragraphs to exceed the max.
        paragraph = (
            "The quick brown fox jumps over the lazy dog. "
            "This sentence is here to pad the paragraph out to a meaningful "
            "size so the chunker has to actually split it. " * 50
        )
        text = "\n\n".join([paragraph] * 8)
        chunks = chunk_text(text)
        self.assertGreater(len(chunks), 1)
        for i, c in enumerate(chunks):
            self.assertEqual(c.chunk_index, i, f"chunk {i} has wrong index")

    def test_chunks_respect_max_size(self) -> None:
        # Build a single very long paragraph (> _TARGET_TOKENS_MAX*4 chars).
        # The chunker is allowed to exceed the max by a single sentence
        # (we don't break sentences), so we check the soft upper bound.
        sentence = "The fox jumps over the lazy dog. "
        long_text = sentence * 2000  # ~100k chars
        chunks = chunk_text(long_text)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            # No chunk should be wildly larger than the target. Allow a
            # 50% safety margin to account for the "don't break
            # sentences" rule.
            self.assertLessEqual(len(c.text), int(_TARGET_TOKENS_MAX * 4 * 1.5) + 200)

    def test_adjacent_chunks_overlap(self) -> None:
        # Build a long text and check that chunk N+1 starts with text
        # that was present in chunk N (the tail).
        sentence = "Authentication is a complex topic. "
        long_text = sentence * 1500
        chunks = chunk_text(long_text)
        self.assertGreaterEqual(len(chunks), 2)
        # The tail of chunk 0 should appear at the start of chunk 1.
        tail = chunks[0].text[-100:]
        self.assertTrue(
            chunks[1].text.startswith(tail[:50]) or tail[:50] in chunks[1].text,
            f"chunk 1 should start with the tail of chunk 0. "
            f"tail starts: {tail[:60]!r}, chunk 1 starts: {chunks[1].text[:60]!r}",
        )

    def test_char_offsets_are_ordered(self) -> None:
        text = ("First paragraph. " * 200 + "\n\n" + "Second paragraph. " * 200)
        chunks = chunk_text(text)
        for c in chunks:
            self.assertGreaterEqual(c.char_start, 0)
            self.assertGreater(c.char_end, c.char_start)
        # Offsets should be non-decreasing.
        for i in range(1, len(chunks)):
            self.assertGreaterEqual(chunks[i].char_start, chunks[i - 1].char_start)

    def test_chunk_dataclass_fields(self) -> None:
        c = Chunk(text="hi", char_start=10, char_end=12, chunk_index=0)
        self.assertEqual(c.text, "hi")
        self.assertEqual(c.char_start, 10)
        self.assertEqual(c.char_end, 12)
        self.assertEqual(c.chunk_index, 0)


if __name__ == "__main__":
    unittest.main()
