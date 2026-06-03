from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from golem.indexer import FileRecord, initialize, transaction, upsert_file
from golem.search import search_with_fallback
from golem.summarizer import HeuristicSummarizer
from golem.watcher import PollingWatcher


class _BadRerankSummarizer(HeuristicSummarizer):
    def search_rerank(self, query: str, candidates: list[dict]) -> str:  # type: ignore[override]
        return "/does/not/exist.txt"


class RuntimeTests(unittest.TestCase):
    def test_search_falls_back_to_not_found_when_rerank_returns_invalid_path(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        conn = initialize(tmpdir / "golem.db")
        record = FileRecord(
            original_filename="alpha.txt",
            clean_filename="Alpha",
            original_path="C:/tmp/alpha.txt",
            current_path="C:/tmp/alpha.txt",
            file_type="txt",
            size_kb=1.0,
            content_hash="hash:1",
            duplicate_of=None,
            extracted_text="alpha beta gamma",
            summary="alpha beta gamma",
            tags="alpha,beta",
            key_contents="alpha, beta",
            category="Other",
            obsidian_note_path="C:/vault/GOLEM/Alpha.md",
            date_indexed="2026-05-31T00:00:00Z",
            last_modified="2026-05-31T00:00:00Z",
            index_status="done",
        )
        with transaction(conn):
            upsert_file(conn, record)

        result = search_with_fallback(conn, "alpha zeta", _BadRerankSummarizer(), 0.8)

        # New contract: SearchResponse with is_not_found helper.
        self.assertTrue(result.is_not_found)
        self.assertTrue(result.results)
        self.assertTrue(result.message)

    def test_watcher_reports_new_files(self) -> None:
        folder = Path(tempfile.mkdtemp()) / "watched"
        folder.mkdir()
        seen: list[Path] = []
        event = threading.Event()

        def on_new_file(path: Path) -> None:
            seen.append(path)
            event.set()

        watcher = PollingWatcher(folder, on_new_file, interval=0.1, debounce_seconds=0.1)
        _poll, worker = watcher.start()
        try:
            time.sleep(0.2)
            new_file = folder / "new.txt"
            new_file.write_text("hello", encoding="utf-8")
            self.assertTrue(event.wait(3.0), "watcher never reported the new file")
            self.assertTrue(seen)
            self.assertEqual(seen[0], new_file)
        finally:
            watcher.stop()

    def test_watcher_debounces_rapid_reports(self) -> None:
        """Touching the same file repeatedly should not enqueue many handler calls."""
        folder = Path(tempfile.mkdtemp()) / "watched"
        folder.mkdir()
        seen: list[Path] = []
        lock = threading.Lock()

        def on_new_file(path: Path) -> None:
            with lock:
                seen.append(path)
            # Block the worker so additional enqueues pile up.
            time.sleep(0.3)

        watcher = PollingWatcher(folder, on_new_file, interval=0.05, debounce_seconds=1.0, queue_size=64)
        watcher.start()
        try:
            time.sleep(0.2)
            new_file = folder / "rapid.txt"
            new_file.write_text("v1", encoding="utf-8")
            time.sleep(0.05)
            new_file.write_text("v2", encoding="utf-8")
            new_file.write_text("v3", encoding="utf-8")
            time.sleep(0.6)
        finally:
            watcher.stop()
        with lock:
            # We expect at most a couple of dispatches (the first change, and
            # maybe one more after the debounce window). Definitely not 4+.
            self.assertLessEqual(len(seen), 3, f"debounce failed: {len(seen)} dispatches")
            self.assertGreaterEqual(len(seen), 1)

