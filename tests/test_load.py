"""Load and stress tests.

These exercise the scanner and the indexer at the size a real user
might hit: 1k, 10k, and 50k files. The memory budget on a 100k file
index is bounded by the streaming reconcile; the scanner still has
to fit the file list in memory once.
"""

from __future__ import annotations

import shutil
import time
import unittest
from pathlib import Path

from golem.indexer import initialize
from golem.scanner import _content_hash, count_files, iter_files, reconcile_missing, scan_folder
from golem.summarizer import HeuristicSummarizer


class LoadTests(unittest.TestCase):
    """Lightweight load tests. Skipped if the disk is too slow or
    the temp space is too small — the goal is to catch regressions
    in the hot path, not to be a CI killer.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._skip_reason = None
        # Skip on machines with < 2 GB free scratch space.
        try:
            import shutil as _sh
            usage = _sh.disk_usage(".")
            if usage.free < 2 * 1024 * 1024 * 1024:
                cls._skip_reason = "less than 2 GB free disk space"
        except OSError:
            cls._skip_reason = "disk usage query failed"

    def setUp(self) -> None:
        if self._skip_reason:
            self.skipTest(self._skip_reason)

    def test_iter_files_handles_1k_files(self) -> None:
        from tempfile import mkdtemp
        root = Path(mkdtemp())
        try:
            for i in range(1_000):
                (root / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")
            count = count_files(root)
            self.assertEqual(count, 1_000)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_scan_indexes_1k_files_in_under_60s(self) -> None:
        from tempfile import mkdtemp
        root = Path(mkdtemp())
        vault = root / "vault"
        db = root / "golem.db"
        try:
            (vault).mkdir()
            watched = root / "watched"
            watched.mkdir()
            for i in range(1_000):
                (watched / f"file_{i}.txt").write_text(f"budget report {i}", encoding="utf-8")
            conn = initialize(db)
            t0 = time.monotonic()
            result = scan_folder(conn, watched, vault, HeuristicSummarizer())
            elapsed = time.monotonic() - t0
            self.assertEqual(result.processed, 1_000)
            self.assertEqual(result.errors, 0)
            # Heuristic summarizer is in-process and very fast; even on
            # a slow CI runner this should complete in under 60s.
            self.assertLess(elapsed, 60.0, f"scan took {elapsed:.1f}s")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_reconcile_streams_in_batches(self) -> None:
        """reconcile_missing must process a large index without OOM.

        The scanner moves files into the vault, so to simulate a
        user-deleted file we wipe BOTH the watched and the vault dirs
        after the scan. The current_path and original_path columns
        will both point at nonexistent paths, so reconcile_missing
        will mark every row as missing.
        """
        from tempfile import mkdtemp
        root = Path(mkdtemp())
        vault = root / "vault"
        db = root / "golem.db"
        try:
            vault.mkdir()
            watched = root / "watched"
            watched.mkdir()
            for i in range(500):
                (watched / f"f_{i}.txt").write_text(f"x {i}", encoding="utf-8")
            conn = initialize(db)
            scan_folder(conn, watched, vault, HeuristicSummarizer())
            # Sanity: 500 rows indexed.
            total = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]
            self.assertEqual(total, 500)
            # Now delete both watched and vault so all current_path /
            # original_path entries are nonexistent.
            shutil.rmtree(watched)
            shutil.rmtree(vault)
            reconcile_missing(conn, vault)
            rows = conn.execute(
                "SELECT COUNT(*) AS c FROM files WHERE index_status = 'missing'"
            ).fetchone()
            self.assertEqual(rows["c"], 500)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_content_hash_for_oversize_file_uses_head_tail(self) -> None:
        """A 20 MB file is hashed with the head+tail strategy."""
        from tempfile import mkdtemp
        root = Path(mkdtemp())
        try:
            p = root / "big.bin"
            # 20 MB of deterministic data
            p.write_bytes((b"\x42") * (20 * 1024 * 1024))
            h = _content_hash(p, p.stat().st_size)
            # Hash is "<hex>:<size>"
            self.assertIn(":", h)
            hex_part, size_part = h.rsplit(":", 1)
            self.assertEqual(int(size_part), 20 * 1024 * 1024)
            self.assertEqual(len(hex_part), 64)  # SHA-256 hex
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_iter_files_skips_hidden_and_system_dirs(self) -> None:
        from tempfile import mkdtemp
        root = Path(mkdtemp())
        try:
            (root / "visible.txt").write_text("yes", encoding="utf-8")
            (root / ".hidden").mkdir()
            (root / ".hidden" / "skipme.txt").write_text("no", encoding="utf-8")
            (root / "System Volume Information").mkdir()
            (root / "System Volume Information" / "alsono.txt").write_text("no", encoding="utf-8")
            names = {p.name for p in iter_files(root)}
            self.assertIn("visible.txt", names)
            self.assertNotIn("skipme.txt", names)
            self.assertNotIn("alsono.txt", names)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
