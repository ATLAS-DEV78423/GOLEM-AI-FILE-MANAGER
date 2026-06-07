"""Centralized AI reliability layer: retry, cache, structured output validation.

The v2 roadmap calls for a single entry point that handles:

- **Retry with exponential backoff** for transient network failures
- **LLM result caching** (exact-match, never-expires) via ``llm_cache`` table
- **Structured output validation** with schema enforcement for JSON metadata
- **Standardized error handling** so file indexing never blocks on a model
  failure

All public functions degrade gracefully: if the cache is unavailable or the
retry budget is exhausted, the caller's fallback (typically the heuristic
summarizer) is invoked without raising.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from .indexer import cache_get as _cache_get
from .indexer import cache_increment_hit as _cache_increment_hit
from .indexer import cache_put as _cache_put
from .indexer import connect as _indexer_connect
from .summarizer import BaseSummarizer, FileMetadata, HeuristicSummarizer
from .utils import humanize_filename, normalize_tags, text_excerpt

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache levels (stored in llm_cache.cache_level)
# ---------------------------------------------------------------------------
CACHE_LEVEL_EXACT = 0  # never expires
CACHE_LEVEL_EPHEMERAL = 2  # 1 hour TTL
_CACHE_TTL_EPHEMERAL = 3600

# ---------------------------------------------------------------------------
# Retry constants
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_MAX_DELAY = 10.0  # seconds

# ---------------------------------------------------------------------------
# Metadata schema validation
# ---------------------------------------------------------------------------
_ALLOWED_CATEGORIES = frozenset(
    {
        "Finance",
        "Research",
        "Design",
        "Code",
        "Media",
        "Personal",
        "Legal",
        "Other",
        "Duplicates",
    }
)

# Sentinel for cache misses (since a cached value could be any JSON value,
# even a falsy one, we need a unique sentinel to distinguish "not cached").
_SENTINEL: Any = {"__golem_sentinel__": True}


def build_cache_key(kind: str, *parts: str) -> str:
    """Build a deterministic cache key from a kind prefix and string parts.

    The key is ``golem:{kind}:{sha256(joined)}`` so that even long prompts
    produce a fixed-size key suitable for SQLite indexing.
    """
    raw = "|".join(parts or [""])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"golem:{kind}:{digest}"


def validate_metadata_dict(data: dict[str, Any]) -> list[str]:
    """Validate a parsed metadata JSON dict against the required schema.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    required = {"summary", "tags", "key_contents", "category", "clean_name"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"missing keys: {', '.join(sorted(missing))}")
    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        errors.append("summary must be a string")
    tags = data.get("tags")
    if tags is not None and not isinstance(tags, list):
        errors.append("tags must be a list")
    if tags is not None and isinstance(tags, list):
        for i, t in enumerate(tags):
            if not isinstance(t, str):
                errors.append(f"tags[{i}] must be a string")
                break
    category = data.get("category")
    if category is not None and category not in _ALLOWED_CATEGORIES:
        errors.append(f"invalid category {category!r}")
    clean_name = data.get("clean_name")
    if clean_name is not None and not isinstance(clean_name, str):
        errors.append("clean_name must be a string")
    return errors


def metadata_to_dict(meta: FileMetadata) -> dict[str, Any]:
    """Convert FileMetadata to a plain dict suitable for JSON caching."""
    return {
        "summary": meta.summary,
        "tags": meta.tags,
        "key_contents": meta.key_contents,
        "category": meta.category,
        "clean_name": meta.clean_name,
    }


def dict_to_metadata(data: dict[str, Any], filename: str) -> FileMetadata | None:
    """Deserialize a cached dict back to FileMetadata.

    Returns ``None`` if the dict is missing required fields (cache
    corruption or schema change).
    """
    try:
        required = {"summary", "tags", "key_contents", "category", "clean_name"}
        if not required.issubset(data.keys()):
            return None
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        category = str(data.get("category") or "Other")
        if category not in _ALLOWED_CATEGORIES:
            category = "Other"
        clean_name = str(data.get("clean_name") or humanize_filename(filename)).strip()
        if not clean_name:
            clean_name = humanize_filename(filename)
        return FileMetadata(
            summary=str(data.get("summary", "")),
            tags=normalize_tags([str(t) for t in tags]),
            key_contents=str(data.get("key_contents", "")),
            category=category,
            clean_name=clean_name,
        )
    except Exception:
        return None


def with_retry(
    fn: Callable[..., Any],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    max_retries: int = _MAX_RETRIES,
) -> Any:
    """Call ``fn(*args, **kwargs)`` with exponential backoff retry.

    Args:
        fn: A callable.
        args: Positional arguments for ``fn``.
        kwargs: Keyword arguments for ``fn``.
        max_retries: Maximum number of attempts (default 3).

    Returns:
        The result from the first successful call.

    Raises:
        The last exception if all retries are exhausted.
    """
    if kwargs is None:
        kwargs = {}
    last_exc: Exception | None = None
    delay = _BASE_DELAY
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                _LOG.warning(
                    "Call failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, _MAX_DELAY)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# CachedSummarizer — wraps any BaseSummarizer with cache + retry + validation
# ---------------------------------------------------------------------------


class CachedSummarizer(BaseSummarizer):
    """A summarizer decorator that adds caching, retry, and output validation.

    Wraps any :class:`BaseSummarizer` (typically an LLM-backed one) and
    intercepts calls to ``get_file_metadata`` and ``search_rerank`` to:

    1. Check the ``llm_cache`` table for an existing result.
    2. On cache miss, call the wrapped summarizer through :func:`with_retry`.
    3. Validate structured output against the schema.
    4. Store the validated result in the cache.
    5. On any unrecoverable error, fall back to heuristic.
    """

    def __init__(
        self,
        summarizer: BaseSummarizer,
        db_path: str | Path,
        *,
        cache_get_fn: Callable | None = None,
        cache_put_fn: Callable | None = None,
        cache_increment_hit_fn: Callable | None = None,
        fallback: BaseSummarizer | None = None,
    ):
        super().__init__()
        self._wrapped = summarizer
        self._db_path = Path(db_path)
        # Allow injection for testability; default to indexer functions.
        self._cache_get = cache_get_fn if cache_get_fn is not None else _cache_get
        self._cache_put = cache_put_fn if cache_put_fn is not None else _cache_put
        self._cache_increment_hit = (
            cache_increment_hit_fn if cache_increment_hit_fn is not None else _cache_increment_hit
        )
        self.fallback = fallback

    @contextmanager
    def _connection(self):
        """Open a temporary connection for cache operations.

        Commits any pending changes on successful exit, rolls back
        on exception, and always closes the connection.
        """
        conn = _indexer_connect(self._db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_file_metadata(self, filename: str, text_snippet: str) -> FileMetadata:
        """Get metadata with cache-first + retry + validation.

        The cache key is built from the filename and an excerpt of the text,
        so identical files across scans produce a cache hit.
        """
        excerpt = text_excerpt(text_snippet, 500)
        cache_key = build_cache_key("metadata", filename, excerpt)

        # 1. Check cache.
        cached = self._try_read_cache(cache_key)
        if cached is not _SENTINEL:
            metadata = dict_to_metadata(cached, filename)
            if metadata is not None:
                return metadata

        # 2. Cache miss: call through with retry.
        try:
            raw = with_retry(
                self._wrapped.get_file_metadata,
                args=(filename, text_snippet),
            )
        except Exception as exc:
            _LOG.warning(
                "Metadata generation failed for %s after retry: %s. Falling back to heuristic.",
                filename,
                exc,
            )
            fb = self._get_fallback()
            return fb.get_file_metadata(filename, text_snippet)

        metadata = cast(FileMetadata, raw)

        # 3. Validate output and cache.
        try:
            data = metadata_to_dict(metadata)
            validation_errors = validate_metadata_dict(data)
            if validation_errors:
                _LOG.warning(
                    "Metadata validation warnings for %s: %s",
                    filename,
                    "; ".join(validation_errors),
                )
            with self._connection() as conn:
                self._cache_put(
                    conn,
                    cache_key,
                    CACHE_LEVEL_EXACT,
                    json.dumps(data, ensure_ascii=False),
                )
        except Exception as exc:
            _LOG.debug("Cache write failed for %s: %s", filename, exc)

        return metadata

    def search_rerank(self, query: str, candidates: list[dict[str, Any]]) -> str:
        """Search rerank with caching and retry."""
        candidate_keys = [
            str(c.get("current_path", c.get("original_path", ""))) for c in candidates[:5]
        ]
        cache_key = build_cache_key("rerank", query, *candidate_keys)

        # 1. Check cache.
        cached = self._try_read_cache(cache_key)
        if cached is not _SENTINEL:
            return str(cached.get("result", "NOT_FOUND"))

        # 2. Cache miss: call through with retry.
        try:
            result = with_retry(
                self._wrapped.search_rerank,
                args=(query, candidates),
                max_retries=2,
            )
        except Exception as exc:
            _LOG.warning("Rerank failed for %r after retry: %s.", query, exc)
            fb = self._get_fallback()
            return fb.search_rerank(query, candidates)

        # 3. Cache (ephemeral — rerank results are query-specific).
        try:
            with self._connection() as conn:
                self._cache_put(
                    conn,
                    cache_key,
                    CACHE_LEVEL_EPHEMERAL,
                    json.dumps({"result": result}, ensure_ascii=False),
                    ttl_seconds=_CACHE_TTL_EPHEMERAL,
                )
        except Exception as exc:
            _LOG.debug("Cache write failed for rerank: %s", exc)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_read_cache(self, key: str) -> dict[str, Any] | Any:
        """Read and deserialize a cache entry. Returns ``_SENTINEL`` on
        miss or deserialization failure."""
        try:
            with self._connection() as conn:
                row = self._cache_get(conn, key)
        except Exception as exc:
            _LOG.debug("Cache read failed for key %s: %s", key, exc)
            return _SENTINEL
        if row is None:
            return _SENTINEL
        try:
            result = json.loads(row["result_json"])
            if not isinstance(result, dict):
                return _SENTINEL
            try:
                with self._connection() as conn:
                    self._cache_increment_hit(conn, key)
            except Exception:
                pass
            return result
        except (json.JSONDecodeError, TypeError, ValueError):
            return _SENTINEL

    def _get_fallback(self) -> BaseSummarizer:
        if self.fallback is not None:
            return self.fallback
        return HeuristicSummarizer()
