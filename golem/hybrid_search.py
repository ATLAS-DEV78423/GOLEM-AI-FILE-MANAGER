"""Hybrid FTS5 + vector search with Reciprocal Rank Fusion.

Search flow:

1. Run FTS5 (BM25) over the ``chunks_fts`` virtual table -> ranked chunks.
2. If :mod:`golem.vector_store` is available, embed the query and run
   vector similarity search -> ranked chunks.
3. Fuse the two lists with Reciprocal Rank Fusion (RRF), a parameter-free
   rank-aggregator described in:

       Cormack, Clarke, Buettcher, "Reciprocal Rank Fusion outperforms
       Condorcet and individual Rank Learning Methods", SIGIR 2009.

   The RRF score for a chunk is::

       score = sum( 1.0 / (RRF_K + rank_in_list) )   # for each list

   where ``rank_in_list`` is 0 for the top hit, 1 for the second, etc.
4. Deduplicate by ``file_path``, keeping the highest-scoring chunk per
   file (so the user gets one row per file in the final results).
5. Return the top-``top_k`` results with their match_type ("keyword",
   "semantic", or "both") so the UI can show a "why matched" pill.

If neither source returns anything, the result is ``[ ]``. The function
never raises; bad FTS queries return ``[ ]`` and vector failures are
swallowed inside :mod:`golem.vector_store`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from . import vector_store

_LOG = logging.getLogger(__name__)

# RRF constant. 60 is the value used in the original paper and is
# well-validated; lower values increase the weight of top-ranked hits.
_RRF_K = 60
_FTS_TOP_K = 50
_VECTOR_TOP_K = 50
_FINAL_TOP_K = 10


@dataclass(slots=True)
class HybridResult:
    """A single hybrid-search hit, ready to be rendered by the UI.

    Attributes:
        file_path: The file's path. The caller can resolve it to a row
            in the ``files`` table for richer metadata.
        chunk_text: A short excerpt of the matching chunk (max 500 chars)
            for the UI's preview line.
        rrf_score: The fused RRF score (higher is better).
        bm25_score: The BM25 score from FTS5 (lower is better, 0 if not
            retrieved by FTS).
        vector_score: The sqlite-vec distance (lower is better, 0 if not
            retrieved by vector search).
        match_type: One of ``"keyword"``, ``"semantic"``, ``"both"``.
    """

    file_path: str
    chunk_text: str
    rrf_score: float
    bm25_score: float
    vector_score: float
    match_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sanitize(query: str) -> list[str]:
    """Tokenize a query into FTS5-friendly lowercase tokens."""
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query) if len(t) > 1][:20]


def _fts_search(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """BM25 search over ``chunks_fts`` -> top ``_FTS_TOP_K`` rows.

    Each returned dict has ``file_path``, ``text``, and ``bm25`` keys.
    Returns ``[ ]`` on an empty / unparseable query.
    """
    tokens = _sanitize(query)
    if not tokens:
        return []
    fts_query = " AND ".join(f"{t}*" for t in tokens)
    try:
        rows = conn.execute(
            """
            SELECT c.file_path, c.text, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (fts_query, _FTS_TOP_K),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        # FTS5 raises on malformed queries (very long, unbalanced
        # quotes, weird syntax). Treat as a clean no-result rather
        # than crashing the caller.
        _LOG.warning("FTS query failed for %r: %s", query, exc)
        return []
    return [
        {"file_path": r["file_path"], "text": r["text"], "bm25": float(r["rank"])} for r in rows
    ]


def _key(hit: dict[str, Any]) -> str:
    """Build the per-chunk identity used for ranking and dedup."""
    return f"{hit.get('file_path', '')}::{hit.get('text', '')[:50]}"


def search(conn: sqlite3.Connection, query: str, top_k: int = _FINAL_TOP_K) -> list[HybridResult]:
    """Run FTS5 + vector search, fuse with RRF, dedupe by file.

    Args:
        conn: An open SQLite connection to the GOLEM database.
        query: The user's search text. Empty / whitespace-only returns ``[ ]``.
        top_k: Maximum number of results to return (default 10).

    Returns:
        A list of :class:`HybridResult` ordered by descending RRF score.
    """
    if not query or not query.strip():
        return []

    fts_hits = _fts_search(conn, query)
    vec_hits: list[dict[str, Any]] = []
    if vector_store.is_available():
        try:
            vec_hits = vector_store.search(conn, query, top_k=_VECTOR_TOP_K)
        except Exception as exc:
            _LOG.warning("vector_store.search failed: %s", exc)
            vec_hits = []

    # Assign a per-list rank (0 = top hit). Items missing from a list
    # are simply not scored in that list.
    fts_by_key = {_key(h): h for h in fts_hits}
    vec_by_key = {_key(h): h for h in vec_hits}
    fts_rank = {k: i for i, k in enumerate(fts_by_key)}
    vec_rank = {k: i for i, k in enumerate(vec_by_key)}

    # Preserve the order in which we first see each key (FTS first,
    # then vector) so output is stable across calls.
    seen: set[str] = set()
    all_keys: list[str] = []
    for k in fts_by_key:
        if k not in seen:
            seen.add(k)
            all_keys.append(k)
    for k in vec_by_key:
        if k not in seen:
            seen.add(k)
            all_keys.append(k)

    scored: list[tuple[float, HybridResult]] = []
    for key in all_keys:
        f = fts_by_key.get(key, {})
        v = vec_by_key.get(key, {})
        f_rank = fts_rank.get(key)
        v_rank = vec_rank.get(key)
        rrf = 0.0
        if f_rank is not None:
            rrf += 1.0 / (_RRF_K + f_rank)
        if v_rank is not None:
            rrf += 1.0 / (_RRF_K + v_rank)
        if f_rank is not None and v_rank is not None:
            mt = "both"
        elif f_rank is not None:
            mt = "keyword"
        else:
            mt = "semantic"
        path = f.get("file_path") or v.get("file_path") or ""
        scored.append(
            (
                rrf,
                HybridResult(
                    file_path=path,
                    chunk_text=(f.get("text") or v.get("text") or "")[:500],
                    rrf_score=rrf,
                    bm25_score=float(f.get("bm25", 0.0) or 0.0),
                    vector_score=float(v.get("score", 0.0) or 0.0),
                    match_type=mt,
                ),
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)

    # Dedupe by file_path, keeping the highest-scoring chunk per file.
    seen_files: set[str] = set()
    out: list[HybridResult] = []
    for _rrf, hr in scored:
        if not hr.file_path:
            continue
        if hr.file_path in seen_files:
            continue
        seen_files.add(hr.file_path)
        out.append(hr)
        if len(out) >= top_k:
            break
    return out
