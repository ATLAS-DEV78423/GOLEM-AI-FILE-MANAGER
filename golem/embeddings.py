"""Local text embeddings with sentence-transformers; no-op fallback.

The v2 hybrid search pipeline embeds both:

  * the user query, at search time
  * every chunk of every indexed file, at indexing time

This module wraps the optional ``sentence-transformers`` library. When
the library is not installed (the default on a fresh checkout), all
embedding functions return zero vectors of the right shape. The hybrid
search still works on FTS5 results alone; semantic results simply
contribute nothing to the RRF score.

The default model is ``all-MiniLM-L6-v2`` (384 dimensions, ~80 MB on
disk, fast on CPU). It is loaded lazily on first use so importing this
module never blocks startup.

Heavy import rule: ``sentence_transformers`` and its transitive deps
(``torch``, ``transformers``, ``numpy``) are imported inside a
``try/except ImportError`` so this module is safe to import even on
machines that do not have the optional ``[semantic]`` extras installed.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

_LOG = logging.getLogger(__name__)

# Output dimension of all-MiniLM-L6-v2. Keep in sync with vector_store._DIM.
_DIM = 384

try:  # pragma: no cover - only present when [semantic] extras are installed
    from sentence_transformers import SentenceTransformer as _SentenceTransformer

    _HAS_ST = True
except ImportError:  # pragma: no cover - default
    _SentenceTransformer = None  # type: ignore[misc]
    _HAS_ST = False

_MODEL_NAME = "all-MiniLM-L6-v2"
_MODEL: Any | None = None

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _STType
    _SentenceTransformerT = _STType
elif _HAS_ST:
    _SentenceTransformerT = type(_SentenceTransformer)
else:
    _SentenceTransformerT = object


def is_available() -> bool:
    """True iff the ``sentence-transformers`` package is importable.

    The hybrid-search layer calls this to feature-gate its vector
    branch; when False, only FTS5 results are used.
    """
    return _HAS_ST


def dimension() -> int:
    """The output dimension of the embedding model.

    Always 384 for the bundled default. Returned as a function rather
    than a constant so future model swaps don't require every caller
    to change.
    """
    return _DIM


def _get_model() -> _SentenceTransformerT | None:
    """Return the cached model, loading it on first use.

    Returns ``None`` when sentence-transformers is not installed.
    """
    global _MODEL
    if not _HAS_ST or _SentenceTransformer is None:
        return None
    if _MODEL is None:
        try:
            _MODEL = _SentenceTransformer(_MODEL_NAME)
        except Exception as exc:  # pragma: no cover - download failures
            _LOG.warning("Failed to load sentence-transformer model %s: %s", _MODEL_NAME, exc)
            return None
    return _MODEL


def embed(text: str) -> list[float]:
    """Embed a single string.

    Returns a length-384 list of floats. When the model is unavailable,
    returns a zero vector of the right shape (which is still a valid
    input to sqlite-vec; it just means the vector branch never wins
    on its own).
    """
    if not _HAS_ST:
        return [0.0] * _DIM
    model = _get_model()
    if model is None:
        return [0.0] * _DIM
    try:
        vec = model.encode([text], normalize_embeddings=True)[0]
    except Exception as exc:  # pragma: no cover
        _LOG.warning("embed() failed: %s", exc)
        return [0.0] * _DIM
    return [float(x) for x in vec]


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed a batch of strings in chunks of ``batch_size``.

    Batching keeps peak memory bounded and is significantly faster than
    one-at-a-time. Returns one length-384 list per input text. If
    ``texts`` is empty, returns ``[ ]``. When the model is unavailable,
    every output is a zero vector (the right shape, the wrong content).
    """
    if not texts:
        return []
    if not _HAS_ST:
        return [[0.0] * _DIM for _ in texts]
    model = _get_model()
    if model is None:
        return [[0.0] * _DIM for _ in texts]
    out: list[list[float]] = []
    try:
        for i in range(0, len(texts), max(1, int(batch_size))):
            batch = list(texts[i : i + batch_size])
            vecs = model.encode(batch, normalize_embeddings=True)
            for v in vecs:
                out.append([float(x) for x in v])
    except Exception as exc:  # pragma: no cover
        _LOG.warning("embed_batch() failed: %s", exc)
        # Pad with zero vectors so the caller still gets the right count.
        while len(out) < len(texts):
            out.append([0.0] * _DIM)
    return out


def content_hash(text: str) -> str:
    """SHA-256 hash of ``text``'s UTF-8 bytes.

    Used to key the LLM/embedding cache so identical chunks re-use
    results across re-indexing runs. Stable across platforms and
    Python versions.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
