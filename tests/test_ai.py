"""Tests for the AI reliability layer (golem/ai.py).

Tests cover:
- build_cache_key determinism
- validate_metadata_dict
- metadata_to_dict / dict_to_metadata round-trip
- with_retry basic and failure paths
- CachedSummarizer cache integration
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from golem.ai import (
    _SENTINEL,
    CachedSummarizer,
    build_cache_key,
    dict_to_metadata,
    metadata_to_dict,
    validate_metadata_dict,
    with_retry,
)
from golem.indexer import initialize
from golem.summarizer import FileMetadata, HeuristicSummarizer


class TestBuildCacheKey(unittest.TestCase):
    def test_deterministic(self) -> None:
        k1 = build_cache_key("metadata", "foo.txt", "bar")
        k2 = build_cache_key("metadata", "foo.txt", "bar")
        self.assertEqual(k1, k2)

    def test_different_inputs_differ(self) -> None:
        k1 = build_cache_key("metadata", "a", "b")
        k2 = build_cache_key("rerank", "a", "b")
        self.assertNotEqual(k1, k2)

    def test_key_format(self) -> None:
        key = build_cache_key("test", "hello")
        self.assertTrue(key.startswith("golem:test:"))


class TestValidateMetadataDict(unittest.TestCase):
    def test_valid_metadata_passes(self) -> None:
        data = {
            "summary": "A test file",
            "tags": ["test", "example"],
            "key_contents": "test",
            "category": "Other",
            "clean_name": "Test",
        }
        self.assertEqual(validate_metadata_dict(data), [])

    def test_missing_keys_reported(self) -> None:
        data = {"summary": "hello"}
        errors = validate_metadata_dict(data)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("missing" in e for e in errors))

    def test_invalid_category_reported(self) -> None:
        data = {
            "summary": "test",
            "tags": ["a"],
            "key_contents": "t",
            "category": "UnknownCategory",
            "clean_name": "Test",
        }
        errors = validate_metadata_dict(data)
        self.assertTrue(any("invalid category" in e for e in errors))

    def test_wrong_types_reported(self) -> None:
        data = {
            "summary": "test",
            "tags": "not-a-list",
            "key_contents": "t",
            "category": "Other",
            "clean_name": "Test",
        }
        errors = validate_metadata_dict(data)
        self.assertTrue(any("list" in e for e in errors))


class TestMetadataConversion(unittest.TestCase):
    def test_round_trip(self) -> None:
        original = FileMetadata(
            summary="test summary",
            tags=["tag1", "tag2"],
            key_contents="key content",
            category="Finance",
            clean_name="Clean Name",
        )
        d = metadata_to_dict(original)
        restored = dict_to_metadata(d, "file.txt")
        assert restored is not None
        self.assertEqual(restored.summary, original.summary)
        self.assertEqual(restored.tags, original.tags)
        self.assertEqual(restored.category, original.category)
        self.assertEqual(restored.clean_name, original.clean_name)

    def test_dict_to_metadata_returns_none_on_bad_data(self) -> None:
        self.assertIsNone(dict_to_metadata({"bad": "data"}, "x.txt"))
        self.assertIsNone(dict_to_metadata({}, "x.txt"))


class TestWithRetry(unittest.TestCase):
    def test_success_on_first_try(self) -> None:
        result = with_retry(lambda: "hello", max_retries=3)
        self.assertEqual(result, "hello")

    def test_success_after_retries(self) -> None:
        attempts: list[int] = []

        def flaky() -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("timeout")
            return "ok"

        result = with_retry(flaky, max_retries=5)
        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)

    def test_raises_after_max_retries(self) -> None:
        def always_fails() -> str:
            raise RuntimeError("always fails")

        with self.assertRaises(RuntimeError):
            with_retry(always_fails, max_retries=2)


class TestCachedSummarizer(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.db_path = self._tmp / "test.db"
        initialize(self.db_path)
        self.heuristic = HeuristicSummarizer()

    def test_cache_hit_returns_cached(self) -> None:
        """When a cache entry exists, get_file_metadata must return it
        without calling the inner summarizer."""
        inner = MagicMock()
        inner.get_file_metadata.return_value = FileMetadata(
            summary="cached",
            tags=["a"],
            key_contents="c",
            category="Other",
            clean_name="Cached",
        )
        summarizer = CachedSummarizer(
            inner,
            self.db_path,
            cache_get_fn=lambda conn, key: {
                "result_json": json.dumps(
                    {
                        "summary": "cached",
                        "tags": ["a"],
                        "key_contents": "c",
                        "category": "Other",
                        "clean_name": "Cached",
                    }
                ),
            },
            cache_put_fn=lambda conn, key, level, result_json, ttl_seconds=None: None,
        )
        result = summarizer.get_file_metadata("test.txt", "hello world")
        self.assertEqual(result.summary, "cached")
        # Inner summarizer should NOT have been called on cache hit.
        inner.get_file_metadata.assert_not_called()

    def test_cache_miss_calls_inner(self) -> None:
        """On cache miss, the inner summarizer must be called."""
        inner = MagicMock()
        inner.get_file_metadata.return_value = FileMetadata(
            summary="fresh",
            tags=["b"],
            key_contents="d",
            category="Finance",
            clean_name="Fresh",
        )
        cached_results: dict[str, tuple[int, str]] = {}

        def cache_put(
            conn, key: str, level: int, result_json: str, ttl_seconds: int | None = None
        ) -> None:
            cached_results[key] = (level, result_json)

        summarizer = CachedSummarizer(
            inner,
            self.db_path,
            cache_get_fn=lambda conn, key: None,  # cache miss
            cache_put_fn=cache_put,
        )
        result = summarizer.get_file_metadata("test.txt", "hello world")
        self.assertEqual(result.summary, "fresh")
        inner.get_file_metadata.assert_called_once()

    def test_search_rerank_cached(self) -> None:
        """search_rerank should hit the cache."""
        inner = MagicMock()
        inner.search_rerank.return_value = "/path/to/file.md"
        summarizer = CachedSummarizer(
            inner,
            self.db_path,
            cache_get_fn=lambda conn, key: {
                "result_json": json.dumps({"result": "/cached/path.md"}),
            },
            cache_put_fn=lambda conn, key, level, result_json, ttl_seconds=None: None,
        )
        result = summarizer.search_rerank("find budget", [{"current_path": "/path"}])
        self.assertEqual(result, "/cached/path.md")
        inner.search_rerank.assert_not_called()

    def test_fallback_on_total_failure(self) -> None:
        """When the inner summarizer raises and caching is unavailable,
        the heuristic fallback should be used."""
        inner = MagicMock()
        inner.get_file_metadata.side_effect = RuntimeError("API unreachable")

        summarizer = CachedSummarizer(
            inner,
            self.db_path,
            cache_get_fn=lambda conn, key: None,
            cache_put_fn=lambda conn, key, level, result_json, ttl_seconds=None: None,
        )
        # Should not raise; should return heuristic result.
        result = summarizer.get_file_metadata("test.txt", "some content")
        self.assertIsNotNone(result.summary)
        self.assertIsNotNone(result.clean_name)

    def test_cache_miss_with_db(self) -> None:
        """Integration: actual DB round-trip for cache miss then hit."""
        inner = MagicMock()
        inner.get_file_metadata.return_value = FileMetadata(
            summary="db test",
            tags=["db"],
            key_contents="db",
            category="Code",
            clean_name="DB Test",
        )
        summarizer = CachedSummarizer(inner, self.db_path)
        # First call: cache miss, calls inner, writes cache.
        result1 = summarizer.get_file_metadata("db_test.txt", "database content")
        self.assertEqual(result1.summary, "db test")
        inner.get_file_metadata.assert_called_once()
        # Second call: cache hit, does NOT call inner.
        result2 = summarizer.get_file_metadata("db_test.txt", "database content")
        self.assertEqual(result2.summary, "db test")
        # Inner should still have been called only once.
        inner.get_file_metadata.assert_called_once()

    def test_sentinel_is_marker_only(self) -> None:
        """_SENTINEL must be a unique dict not equal to any real cached data."""
        self.assertIsInstance(_SENTINEL, dict)
        self.assertTrue(_SENTINEL.get("__golem_sentinel__"))


if __name__ == "__main__":
    unittest.main()
