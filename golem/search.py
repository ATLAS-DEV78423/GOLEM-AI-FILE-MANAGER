from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any

from . import hybrid_search
from .indexer import get_neighbors, recent_files, search_files
from .summarizer import BaseSummarizer


def _normalize_path(p: str) -> str:
    """Normalize a path for tolerant equality comparison.

    On Windows the filesystem is case-insensitive, so "C:\\Foo\\bar.txt"
    and "c:\\foo\\BAR.txt" refer to the same file. We also collapse
    forward and backward slashes because LLMs are inconsistent about
    which they use when returning paths.

    On case-sensitive filesystems (Linux) we still casefold paths that
    look like Windows paths (contain a drive-letter prefix like "C:/"),
    because LLMs may return Windows-format paths regardless of the host
    platform.
    """
    if not p:
        return ""
    s = str(p).replace("\\", "/")
    # Casefold on case-insensitive filesystems (Windows, macOS).
    # Also casefold Windows-style paths (drive-letter prefix) that LLMs
    # may return regardless of the host platform (e.g., on Linux CI).
    if sys.platform.startswith("win") or sys.platform == "darwin" or (
        len(s) >= 2 and s[1] == ":" and s[0].isalpha()
    ):
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
    match_type: str = ""
    chunk_text: str = ""
    rrf_score: float = 0.0
    bm25_score: float = 0.0
    vector_score: float = 0.0
    confidence: float = 0.0
    rank: float = 0.0
    related: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_related(self) -> bool:
        return len(self.related) > 0

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
            match_type=str(row.get("match_type", "")),
            chunk_text=str(row.get("chunk_text", "")),
            rrf_score=float(row.get("rrf_score", 0.0) or 0.0),
            bm25_score=float(row.get("bm25_score", 0.0) or 0.0),
            vector_score=float(row.get("vector_score", 0.0) or 0.0),
            confidence=float(row.get("confidence", 0.0) or 0.0),
            rank=float(row.get("rank", 0.0) or 0.0),
            related=row.get("related", []),
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


def _confidence_for_hybrid(hit: Any) -> float:
    match_type = str(getattr(hit, "match_type", "") or "")
    base = {
        "both": 0.92,
        "keyword": 0.86,
        "semantic": 0.8,
    }.get(match_type, 0.75)
    rrf_score = float(getattr(hit, "rrf_score", 0.0) or 0.0)
    return min(1.0, base + min(rrf_score * 5.0, 0.08))


def _hybrid_candidates(conn, query: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hybrid_search.search(conn, query, top_k=10):
        row = conn.execute(
            """
            SELECT id, original_filename, clean_filename, original_path, current_path,
                   summary, tags, key_contents, category, obsidian_note_path, index_status
            FROM files
            WHERE original_path = ? OR current_path = ?
            LIMIT 1
            """,
            (hit.file_path, hit.file_path),
        ).fetchone()
        candidate: dict[str, Any]
        if row is not None:
            candidate = dict(row)
        else:
            candidate = {
                "id": 0,
                "original_filename": Path(hit.file_path).name,
                "clean_filename": Path(hit.file_path).stem,
                "original_path": hit.file_path,
                "current_path": hit.file_path,
                "summary": "",
                "tags": "",
                "key_contents": "",
                "category": "",
                "obsidian_note_path": "",
                "index_status": "",
            }
        candidate.update(
            {
                "match_type": hit.match_type,
                "chunk_text": hit.chunk_text,
                "rrf_score": hit.rrf_score,
                "bm25_score": hit.bm25_score,
                "vector_score": hit.vector_score,
                "confidence": _confidence_for_hybrid(hit),
                "rank": -hit.rrf_score,
            }
        )
        out.append(candidate)

    # ── Folder-proximity boost ────────────────────────────────────
    # If the top result has a parent directory, boost other results
    # that share the same directory, subdirectory, or parent directory
    # so users see files that are contextually nearby.
    if out:
        top_path = str(out[0].get("current_path") or out[0].get("original_path") or "")
        try:
            top_parent = str(Path(top_path).parent.resolve())
        except OSError:
            top_parent = ""
        if top_parent:
            for c in out[1:]:
                c_path = str(c.get("current_path") or c.get("original_path") or "")
                try:
                    c_parent = str(Path(c_path).parent.resolve())
                except OSError:
                    continue
                # Exact same directory: largest boost
                if c_parent == top_parent:
                    c["confidence"] = min(1.0, float(c.get("confidence", 0.0) or 0.0) + 0.08)
                    c["rrf_score"] = float(c.get("rrf_score", 0.0) or 0.0) + 0.5
                # Same grandparent (sibling dir): moderate boost
                elif Path(c_parent).parent == Path(top_parent).parent:
                    c["confidence"] = min(1.0, float(c.get("confidence", 0.0) or 0.0) + 0.04)
                    c["rrf_score"] = float(c.get("rrf_score", 0.0) or 0.0) + 0.2

    # Re-sort by updated confidence after proximity boost
    out.sort(key=lambda x: (-float(x.get("confidence", 0.0) or 0.0), -float(x.get("rrf_score", 0.0) or 0.0)))
    return out


def _enrich_with_graph(conn, results: list[dict[str, Any]], depth: int = 2) -> list[dict[str, Any]]:
    """Add graph neighbor data to search results.

    For each result, queries ``get_neighbors`` and attaches the related
    nodes as a ``related`` list of ``{"label": ..., "type": ...}`` dicts.
    ``depth=2`` traverses tag → related files and category → member files,
    surfacing indirect but contextually relevant connections.
    This is best-effort: if the graph is empty or the query fails, the
    result is returned unmodified.
    """
    out: list[dict[str, Any]] = []
    for row in results:
        path = str(row.get("original_path") or row.get("current_path") or "")
        if path:
            try:
                nodes = get_neighbors(conn, path, depth=depth)
                related = []
                seen_labels: set[str] = set()
                for n in nodes:
                    n_path = str(n["file_path"] or "")
                    n_type = str(n["type"] or "")
                    n_label = str(n["label"] or "")
                    if n_path == path:
                        continue
                    if n_type in ("tag", "project"):
                        key = f"{n_type}:{n_label}"
                        if key not in seen_labels:
                            seen_labels.add(key)
                            related.append({"label": n_label, "type": n_type, "file_path": n_path})
                    elif n_type == "file":
                        label = n_label or Path(n_path).stem
                        key = f"file:{label}"
                        if key not in seen_labels:
                            seen_labels.add(key)
                            related.append({"label": label, "type": "related_file", "file_path": n_path})
                # Sort related: tags first, then projects, then files
                type_order = {"tag": 0, "project": 1, "related_file": 2}
                related.sort(key=lambda x: (type_order.get(x["type"], 99), x["label"]))
                row["related"] = related[:12]
            except Exception:
                row["related"] = []
        else:
            row["related"] = []
        out.append(row)
    return out


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
    candidates = _hybrid_candidates(conn, query)
    if not candidates:
        candidates = search_files(conn, query, limit=10)
    # Enrich with graph context
    if candidates:
        candidates = _enrich_with_graph(conn, candidates)
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
