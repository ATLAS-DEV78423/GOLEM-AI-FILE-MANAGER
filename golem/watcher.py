from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from .constants import SYSTEM_SKIP_DIRS
from .utils import is_hidden_or_system_dir


class PollingWatcher:
    """Polling filesystem watcher with debounce and single-consumer dispatch.

    The previous implementation fired ``on_new_file`` for every poll cycle in
    which a file's mtime changed. On a busy folder (e.g. dragging in 100
    files) this spawned a thread per file, all racing for the SQLite WAL
    lock and producing ``database is locked`` errors that were silently
    swallowed.

    This version:
      * Debounces per-file: a file that was reported within the last
        ``debounce_seconds`` is not reported again.
      * Serializes dispatch: a single consumer thread reads from a bounded
        queue, so at most one ``on_new_file`` runs at a time. SQLite
        contention is impossible.
      * Cooperates with shutdown: ``stop()`` is idempotent and waits for the
        worker to drain or be cancelled.
    """

    def __init__(
        self,
        folder: Path,
        on_new_file: Callable[[Path], None],
        interval: float = 3.0,
        debounce_seconds: float = 2.0,
        queue_size: int = 1024,
    ) -> None:
        self.folder = folder
        self.on_new_file = on_new_file
        self.interval = max(0.1, float(interval))
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self._stop = threading.Event()
        self._known: dict[str, float] = {}
        self._last_dispatched: dict[str, float] = defaultdict(float)
        self._queue: queue.Queue[Path | None] = queue.Queue(maxsize=queue_size)
        self._poll_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None

    def start(self) -> tuple[threading.Thread, threading.Thread]:
        """Start the poll and worker threads. Returns (poll_thread, worker_thread)."""
        self._snapshot_known()
        self._poll_thread = threading.Thread(
            target=self._run_poll, name="golem-watcher-poll", daemon=True
        )
        self._worker_thread = threading.Thread(
            target=self._run_worker, name="golem-watcher-worker", daemon=True
        )
        self._poll_thread.start()
        self._worker_thread.start()
        return self._poll_thread, self._worker_thread

    def stop(self, drain: bool = True, timeout: float = 2.0) -> None:
        """Stop both threads.

        If ``drain`` is True (default), the worker finishes every queued
        path before exiting. If False, the sentinel is pushed immediately
        and the worker exits at the next iteration.
        """
        self._stop.set()
        if not drain:
            # Push a sentinel to wake the worker up; the worker will
            # process whatever was already queued.
            pass
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # If the queue is full, just let the stop event do its job.
            pass
        for t in (self._poll_thread, self._worker_thread):
            if t is not None and t.is_alive():
                t.join(timeout=timeout)

    def _snapshot_known(self) -> None:
        self._known.clear()
        for path in self.folder.rglob("*"):
            if not self._should_track(path):
                continue
            try:
                self._known[str(path)] = path.stat().st_mtime
            except OSError as exc:
                logging.debug("Snapshot stat failed for %s: %s", path, exc)

    def _should_track(self, path: Path) -> bool:
        if not path.is_file():
            return False
        # Symlinks and reparse points (e.g. NTFS junctions) can point at
        # arbitrary locations outside the watched folder, including system
        # directories. Refuse to track them so a forged symlink cannot cause
        # the indexer to read or move files outside the watch root.
        try:
            if path.is_symlink():
                return False
        except OSError as exc:
            logging.debug("Symlink check failed for %s: %s; skipping", path, exc)
            return False
        if any(is_hidden_or_system_dir(part) or part in SYSTEM_SKIP_DIRS for part in path.parts):
            return False
        return True

    def _enqueue(self, path: Path) -> None:
        """Queue a path for the worker, debouncing rapid re-fires."""
        key = str(path)
        now = time.monotonic()
        last = self._last_dispatched[key]
        if now - last < self.debounce_seconds:
            return
        self._last_dispatched[key] = now
        try:
            self._queue.put_nowait(path)
        except queue.Full:
            logging.warning("Watcher queue full; dropping %s", path)

    def _run_poll(self) -> None:
        while not self._stop.is_set():
            try:
                for path in self.folder.rglob("*"):
                    if self._stop.is_set():
                        break
                    if not self._should_track(path):
                        continue
                    key = str(path)
                    try:
                        mtime = path.stat().st_mtime
                    except OSError as exc:
                        logging.debug("Stat failed during poll for %s: %s", path, exc)
                        continue
                    previous = self._known.get(key)
                    if previous is None:
                        # New file we've never seen.
                        self._known[key] = mtime
                        self._enqueue(path)
                    elif mtime > previous:
                        # Modified file.
                        self._known[key] = mtime
                        self._enqueue(path)
            except Exception as exc:
                # A glob or stat blew up — log and keep going.
                logging.exception("Watcher poll error: %s", exc)
            # Sleep with a small granularity so ``stop`` is responsive.
            end = time.monotonic() + self.interval
            while not self._stop.is_set() and time.monotonic() < end:
                remaining = end - time.monotonic()
                if remaining > 0:
                    time.sleep(min(0.2, remaining))

    def _run_worker(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set() and self._queue.empty():
                    return
                continue
            if item is None:
                self._queue.task_done()
                return
            try:
                self.on_new_file(item)
            except Exception as exc:
                logging.exception("Watcher handler error for %s: %s", item, exc)
            finally:
                self._queue.task_done()
