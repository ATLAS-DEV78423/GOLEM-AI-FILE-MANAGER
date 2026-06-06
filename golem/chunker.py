"""Recursive paragraph -> sentence chunker with overlap.

Used by the v2 semantic search pipeline to split extracted file text into
~256-512 token chunks suitable for embedding and FTS5 indexing. Adjacent
chunks share ~15% character overlap so a query that falls on a chunk
boundary still matches.

This module is pure stdlib (re + dataclasses); it never imports any of the
optional heavy dependencies (sentence-transformers, sqlite-vec, etc.). It
must remain safe to call when those extras are absent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Target chunk size in *approximate* tokens. 1 token ~= 4 chars in English,
# which is good enough for sizing; the embedding model is the source of
# truth for actual token counts.
_TARGET_TOKENS_MIN = 256
_TARGET_TOKENS_MAX = 512
# Overlap between adjacent chunks as a fraction of chunk length.
_OVERLAP_RATIO = 0.15


@dataclass(slots=True)
class Chunk:
    """A single chunk of text with positional metadata.

    Attributes:
        text: The chunk text. Whitespace is preserved as-is from the input.
        char_start: Inclusive start offset in the source text.
        char_end: Exclusive end offset in the source text.
        chunk_index: Zero-based index of this chunk within its file.
    """

    text: str
    char_start: int
    char_end: int
    chunk_index: int


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARA_SPLIT = re.compile(r"\n\s*\n")


def _approx_tokens(s: str) -> int:
    """Roughly estimate the number of tokens in a string.

    Uses a 4-chars-per-token heuristic, which is close enough for English
    text to keep chunk sizes in the target band. Empty strings map to 0.
    """
    if not s:
        return 0
    return max(1, len(s) // 4)


def chunk_text(text: str, file_path: str = "") -> list[Chunk]:
    """Split ``text`` into paragraph -> sentence chunks of 256-512 tokens.

    Args:
        text: The full extracted text of a file.
        file_path: Optional source path (for logging / debugging). Not used
            by the chunker itself; kept for symmetry with the v2 logging
            helpers.

    Returns:
        A list of :class:`Chunk` objects. Returns an empty list when
        ``text`` is empty or whitespace-only.

    Notes:
        The algorithm first splits on blank lines (paragraphs). For each
        paragraph, sentences are split off if the paragraph exceeds the
        max chunk size in characters. Sentences are then accumulated into
        a buffer; whenever adding the next sentence would push the buffer
        past ``_TARGET_TOKENS_MAX``, the buffer is emitted as a chunk and
        the last ``_OVERLAP_RATIO`` of its characters is carried over into
        the next buffer.
    """
    if not text or not text.strip():
        return []
    # Split into non-empty paragraphs and trim them.
    paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_start = 0
    char_cursor = 0
    idx = 0

    for para in paragraphs:
        # Locate the paragraph's start in the original text. The clause
        # is defensive: a stray whitespace difference (e.g. unicode
        # normalization) should not throw here.
        para_start = text.index(para, char_cursor) if para in text[char_cursor:] else char_cursor
        char_cursor = para_start + len(para)
        # Only split into sentences for paragraphs that are larger than
        # the max chunk size; short paragraphs are kept whole.
        if len(para) > _TARGET_TOKENS_MAX * 4:
            sentences = _SENTENCE_SPLIT.split(para)
        else:
            sentences = [para]

        for sent in sentences:
            if not sent.strip():
                continue
            tentative = _approx_tokens(" ".join(buf + [sent]))
            if tentative > _TARGET_TOKENS_MAX and buf:
                joined = " ".join(buf)
                chunks.append(
                    Chunk(
                        text=joined,
                        char_start=buf_start,
                        char_end=buf_start + len(joined),
                        chunk_index=idx,
                    )
                )
                idx += 1
                # Carry overlap: keep the tail of the just-emitted chunk
                # so the next chunk starts with shared context.
                overlap_chars = int(len(joined) * _OVERLAP_RATIO)
                tail = joined[-overlap_chars:] if overlap_chars else ""
                buf = [tail] if tail else []
                if tail:
                    buf_start = buf_start + len(joined) - len(tail)
                else:
                    buf_start = char_cursor
            if not buf:
                # Position the start of the buffer at the sentence's
                # location within the paragraph (best effort).
                buf_start = para_start + (para.index(sent) if sent in para else 0)
            buf.append(sent)

    if buf:
        joined = " ".join(buf)
        chunks.append(
            Chunk(
                text=joined,
                char_start=buf_start,
                char_end=buf_start + len(joined),
                chunk_index=idx,
            )
        )
    return chunks
