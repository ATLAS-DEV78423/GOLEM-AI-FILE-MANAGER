from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from .indexer import recent_files, search_files
from .summarizer import BaseSummarizer


def _normalize_path(p: str) -> str:
    """Normalize a path for tolerant equality comparison.

    On Windows the filesystem is case-insensitive, so "C:\\Foo\\bar.txt"
    and "c:\\foo\\BAR.txt" refer to the same file. We also collapse
    forward and backward slashes because LLMs are inconsistent about
    which they use when returning paths. On POSIX we only normalize
    separators; case is preserved.
    """
    if not p:
        return ""
    s = str(p).replace("\\", "/")
    if sys.platform.startswith("win") or sys.platform == "darwin":
        # macOS HFS+/APFS is case-insensitive by default.
        s = s.casefold()
    return s.rstrip("/")


@dataclass(slots=True)
class SearchResult:
    """A single file hit returned by search_with_fallback.

    Carries every field the UI needs to render the row in the listbox plus the
    confidence score. Always the same shape — see SearchResponse below.
    """

    id: int
    original_filename: str
    clean_filename: str
    original_path: str
    current_path: str
    summary: str
    tags: str
    key_contents: str
    category: str
    obsidian_note_path: str
    index_status: str
    confidence: float = 0.0
    rank: float = 0.0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SearchResult:
        return cls(
            id=int(row["id"]),
            original_filename=str(row.get("original_filename", "")),
            clean_filename=str(row.get("clean_filename", "")),
            original_path=str(row.get("original_path", "")),
            current_path=str(row.get("current_path", "")),
            summary=str(row.get("summary", "")),
            tags=str(row.get("tags", "")),
            key_contents=str(row.get("key_contents", "")),
            category=str(row.get("category", "")),
            obsidian_note_path=str(row.get("obsidian_note_path", "")),
            index_status=str(row.get("index_status", "")),
            confidence=float(row.get("confidence", 0.0) or 0.0),
            rank=float(row.get("rank", 0.0) or 0.0),
        )


@dataclass(slots=True)
class SearchResponse:
    """The unified return shape of search_with_fallback.

    `status` is one of:
      - "ok"            : `results` contains the matching files (length may be 0)
      - "not_found"     : no match; `results` holds recent files as a fallback,
                          and `message` explains the situation to the user
    """

    status: str
    results: list[SearchResult] = field(default_factory=list)
    message: str = ""

    @property
    def is_not_found(self) -> bool:
        return self.status == "not_found"

    def to_payload(self) -> dict[str, Any]:
        """Serialize for the UI/JSON consumers. The listbox reads `results`.

        The `status` and `message` fields are first-class — the UI checks
        `is_not_found` instead of duck-typing.
        """
        return {
            "status": self.status,
            "results": [asdict(r) for r in self.results],
            "message": self.message,
        }


def _to_results(rows: list[dict[str, Any]]) -> list[SearchResult]:
    return [SearchResult.from_row(row) for row in rows]


def search_with_fallback(
    conn,
    query: str,
    summarizer: BaseSummarizer,
    confidence_threshold: float = 0.8,
) -> SearchResponse:
    """Search the index, falling back to an LLM rerank when confidence is low.

    Always returns a SearchResponse. The UI can read `response.is_not_found`
    to decide whether to show the recents list.
    """
    candidates = search_files(conn, query, limit=10)
    if not candidates:
        return SearchResponse(
            status="not_found",
            results=_to_results(recent_files(conn, 3)),
            message="No exact match. Showing recent files.",
        )

    top = candidates[0]
    if top.get("confidence", 0.0) >= confidence_threshold:
        return SearchResponse(status="ok", results=_to_results(candidates))

    reranked = summarizer.search_rerank(query, candidates[:5])
    if reranked == "NOT_FOUND":
        return SearchResponse(
            status="not_found",
            results=_to_results(recent_files(conn, 3)),
            message="No close match. Showing recent files.",
        )

    # Validate the LLM's rerank against the candidate set. The LLM is asked to
    # return a file path, but it may return anything — a hallucinated path, a
    # paraphrase, a note path. Only accept exact matches against the candidates
    # we actually gave it. The comparison is case-insensitive on Windows /
    # macOS and tolerant of \ vs /.
    reranked_norm = _normalize_path(str(reranked).strip())
    for candidate in candidates:
        if (
            _normalize_path(str(candidate.get("current_path") or ""))
            == reranked_norm
            or _normalize_path(str(candidate.get("original_path") or ""))
            == reranked_norm
        ):
            boosted = dict(candidate)
            boosted["confidence"] = 1.0
            others = [c for c in candidates if c is not candidate]
            return SearchResponse(
                status="ok",
                results=_to_results([boosted] + others),
            )

    return SearchResponse(
        status="not_found",
        results=_to_results(recent_files(conn, 3)),
        message="Rerank returned an invalid result. Showing recent files.",
    )
