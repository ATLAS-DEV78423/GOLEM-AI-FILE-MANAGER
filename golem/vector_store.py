"""Vector storage with sqlite-vec when available, no-op otherwise.

The v2 hybrid search pipeline calls this module to store and retrieve
chunk embeddings. When the optional ``sqlite-vec`` extension is not
installed, the module degrades to a no-op: ``upsert``/``delete`` do
nothing, and ``search_by_embedding`` always returns ``[ ]``.

The 384-dim default matches the ``all-MiniLM-L6-v2`` sentence-transformer
model used by :mod:`golem.embeddings`. If you switch embedding models,
update ``_DIM`` here too.

The ``search`` function in this module is a convenience that embeds the
query text via :mod:`golem.embeddings` and then calls
``search_by_embedding``. If the embedding model is unavailable, this
returns ``[ ]`` — semantic search is silently disabled.
"""

from __future__ import annotations

import logging
import struct
from typing import Any

_LOG = logging.getLogger(__name__)

# Default dimension for all-MiniLM-L6-v2.
_DIM = 384

try:  # pragma: no cover - exercised on machines with the extension
    import sqlite_vec

    _HAS_VEC = True
except ImportError:  # pragma: no cover - default case
    _HAS_VEC = False

# sqlite-vec must be registered on each SQLite connection, but the
# virtual table definition itself only needs to be created once per
# connection. Cache loaded connection ids so repeated upserts/searches
# stay cheap without assuming a single long-lived connection.
_LOADED_CONNECTIONS: set[int] = set()


def is_available() -> bool:
    """Return True iff the sqlite-vec extension is importable.

    Use this to feature-gate code that wants to do vector search. The
    rest of the API is safe to call when ``is_available()`` is False
    (functions return empty results or no-op).
    """
    return _HAS_VEC


def _ensure_schema(conn) -> None:
    """Install the ``vec_chunks`` virtual table on ``conn`` (idempotent)."""
    if not _HAS_VEC:
        return
    conn_id = id(conn)
    if conn_id in _LOADED_CONNECTIONS:
        return
    try:
        conn.enable_load_extension(True)
    except Exception as exc:  # pragma: no cover - platform-dependent
        _LOG.warning("enable_load_extension failed: %s", exc)
        return
    try:
        sqlite_vec.load(conn)
    except Exception as exc:  # pragma: no cover - extension load failures
        _LOG.warning("Failed to load sqlite-vec: %s", exc)
        return
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
            f"USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{_DIM}])"
        )
    except Exception as exc:  # pragma: no cover
        _LOG.warning("Failed to create vec_chunks table: %s", exc)
        return
    _LOADED_CONNECTIONS.add(conn_id)


def _pack(vec: list[float]) -> bytes:
    """Pack a list of floats into the little-endian ``<Nf`` layout sqlite-vec expects."""
    return struct.pack(f"<{len(vec)}f", *vec)


def upsert(conn, chunk_id: int, text: str, embedding: list[float]) -> None:
    """Insert or replace a chunk embedding.

    No-op when sqlite-vec is unavailable. ``text`` is accepted but not
    persisted here; the ``chunks`` table already holds the text. It is
    included in the signature for symmetry with the embedding pipeline.
    """
    if not _HAS_VEC:
        return
    _ensure_schema(conn)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, _pack(embedding)),
        )
    except Exception as exc:
        _LOG.warning("vec_chunks upsert failed for chunk %d: %s", chunk_id, exc)


def delete_for_path(conn, file_path: str) -> None:
    """Remove all vec_chunks rows whose chunk_id belongs to ``file_path``."""
    if not _HAS_VEC:
        return
    _ensure_schema(conn)
    try:
        conn.execute(
            "DELETE FROM vec_chunks WHERE chunk_id IN (SELECT id FROM chunks WHERE file_path = ?)",
            (file_path,),
        )
    except Exception as exc:
        _LOG.warning("vec_chunks delete_for_path failed for %s: %s", file_path, exc)


def delete_for_chunk(conn, chunk_id: int) -> None:
    """Remove a single vec_chunks row by chunk_id."""
    if not _HAS_VEC:
        return
    _ensure_schema(conn)
    try:
        conn.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (chunk_id,))
    except Exception as exc:
        _LOG.warning("vec_chunks delete_for_chunk failed: %s", exc)


def search_by_embedding(
    conn,
    query_embedding: list[float],
    top_k: int = 50,
) -> list[dict[str, Any]]:
    """Return the top-``top_k`` chunks most similar to ``query_embedding``.

    Each result dict has the shape ``{"file_path": str, "text": str,
    "score": float}`` where ``score`` is the *distance* reported by
    sqlite-vec (lower is better; the hybrid search layer converts this
    to a rank). Returns ``[ ]`` when sqlite-vec is unavailable.
    """
    if not _HAS_VEC or not query_embedding:
        return []
    _ensure_schema(conn)
    try:
        rows = conn.execute(
            "SELECT chunk_id, distance FROM vec_chunks "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (_pack(query_embedding), int(top_k)),
        ).fetchall()
    except Exception as exc:
        _LOG.warning("vec_chunks search failed: %s", exc)
        return []
    if not rows:
        return []
    chunk_ids = [r[0] for r in rows]
    placeholders = ",".join("?" for _ in chunk_ids)
    chunks = conn.execute(
        f"SELECT id, file_path, text FROM chunks WHERE id IN ({placeholders})",  # noqa: S608
        chunk_ids,
    ).fetchall()
    by_id = {c["id"]: dict(c) for c in chunks}
    out: list[dict[str, Any]] = []
    for r in rows:
        c = by_id.get(r[0])
        if c is None:
            continue
        out.append(
            {
                "file_path": c["file_path"],
                "text": c["text"],
                "score": float(r[1]),
            }
        )
    return out


def search(conn, query: str, top_k: int = 50) -> list[dict[str, Any]]:
    """Embed ``query`` and return the top-k closest chunks.

    Convenience wrapper used by :mod:`golem.hybrid_search`. Imports
    :mod:`golem.embeddings` lazily to avoid a hard dependency on
    sentence-transformers at import time.
    """
    if not _HAS_VEC:
        return []
    try:
        from . import embeddings
    except Exception as exc:  # pragma: no cover
        _LOG.warning("embeddings import failed in vector_store.search: %s", exc)
        return []
    if not embeddings.is_available():
        return []
    try:
        qvec = embeddings.embed(query)
    except Exception as exc:  # pragma: no cover
        _LOG.warning("query embedding failed: %s", exc)
        return []
    return search_by_embedding(conn, qvec, top_k=top_k)
