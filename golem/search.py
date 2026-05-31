from __future__ import annotations

from typing import Any

from .indexer import recent_files, search_files
from .summarizer import BaseSummarizer


def search_with_fallback(conn, query: str, summarizer: BaseSummarizer, confidence_threshold: float = 0.8) -> list[dict[str, Any]]:
    candidates = search_files(conn, query, limit=10)
    if not candidates:
        recent = recent_files(conn, 3)
        return [{"status": "not_found", "results": recent, "message": "No exact match. Showing recent files."}]
    top = candidates[0]
    if top.get("confidence", 0.0) >= confidence_threshold:
        return candidates
    reranked = summarizer.search_rerank(query, candidates[:5])
    if reranked == "NOT_FOUND":
        recent = recent_files(conn, 3)
        return [{"status": "not_found", "results": recent, "message": "No exact match. Showing recent files."}]
    for candidate in candidates:
        if candidate.get("current_path") == reranked or candidate.get("original_path") == reranked:
            candidate["confidence"] = 1.0
            return [candidate] + [row for row in candidates if row is not candidate]
    recent = recent_files(conn, 3)
    return [{"status": "not_found", "results": recent, "message": "No exact match. Showing recent files."}]
