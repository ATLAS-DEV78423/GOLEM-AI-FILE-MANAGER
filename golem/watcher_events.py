"""Event-driven file watcher using watchdog, with write-stability buffering.

The v2 indexing pipeline wants to re-index a file once the writer has
finished saving it. Polling for mtime changes works but is wasteful
(3-second cycle even when nothing happens) and on Windows the
``ReadDirectoryChangesW`` events are bursty / out-of-order, so we
buffer them and only fire ``on_stable`` after the file has been quiet
for ``_STABILITY_SECONDS``.

If watchdog is not installed (the default on a fresh checkout), the
``start_event_watcher`` function returns ``None`` and the caller should
fall back to :class:`golem.watcher.PollingWatcher`. This keeps the
event-driven path strictly optional.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Time (in seconds) a file must be quiet before we consider it "stable"
# and dispatch the on_new_file callback. The Windows write event
# pattern is: created, modified, modified, modified, settled — so 2
# seconds is the smallest value that reliably skips the in-flight
# state. Linux/macOS could safely use a smaller value, but we keep
# the same threshold for predictability across platforms.
_STABILITY_SECONDS = 2.0

# Interval between scans of the pending dict. Smaller = more responsive
# but more wakeups. 500 ms is a good trade-off for a desktop app.
_PUMP_INTERVAL_SECONDS = 0.5

try:  # pragma: no cover - watchdog is optional
    from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
    from watchdog.observers import Observer  # type: ignore[import-untyped]

    _HAS_WATCHDOG = True
except ImportError:  # pragma: no cover
    # When watchdog is not installed, use ``object`` as a valid base so
    # the class definition below never sees ``None`` as a base class.
    # ``start_event_watcher`` still returns ``None`` when ``_HAS_WATCHDOG``
    # is False, so ``_StableHandler`` is never instantiated.
    FileSystemEventHandler = object  # type: ignore[misc,assignment]
    Observer = None  # type: ignore[assignment]
    _HAS_WATCHDOG = False


class _StableHandler(FileSystemEventHandler):
    """Watchdog handler that buffers events and fires once per stable file.

    The ``on_created`` / ``on_modified`` / ``on_moved`` callbacks all
    just stamp a ``time.monotonic()`` value into a thread-safe dict.
    A separate pump thread scans the dict every
    ``_PUMP_INTERVAL_SECONDS`` and dispatches ``on_stable`` for any
    path that has been quiet for ``_STABILITY_SECONDS``.
    """

    def __init__(
        self,
        on_stable: Callable[[Path], None],
        stop: threading.Event,
    ) -> None:
        self._on_stable = on_stable
        self._stop = stop
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._pump = threading.Thread(
            target=self._pump_loop,
            daemon=True,
            name="golem-watchdog-stable-pump",
        )
        self._pump.start()

    def _schedule(self, path: Path) -> None:
        # Defensive: filter out directories and missing files. Some
        # platforms emit created events for dirs that immediately
        # disappear.
        try:
            if not path.is_file():
                return
        except OSError:
            return
        with self._lock:
            self._pending[str(path)] = time.monotonic()

    def on_created(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        try:
            self._schedule(Path(event.src_path))
        except Exception as exc:  # pragma: no cover
            _LOG.debug("on_created path error: %s", exc)

    def on_modified(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        try:
            self._schedule(Path(event.src_path))
        except Exception as exc:  # pragma: no cover
            _LOG.debug("on_modified path error: %s", exc)

    def on_moved(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        try:
            self._schedule(Path(event.dest_path))
        except Exception as exc:  # pragma: no cover
            _LOG.debug("on_moved path error: %s", exc)

    def _pump_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(_PUMP_INTERVAL_SECONDS)
            now = time.monotonic()
            ready: list[str] = []
            with self._lock:
                for key, ts in list(self._pending.items()):
                    if now - ts >= _STABILITY_SECONDS:
                        ready.append(key)
                for key in ready:
                    del self._pending[key]
            for key in ready:
                try:
                    self._on_stable(Path(key))
                except Exception as exc:
                    _LOG.exception("on_stable handler error for %s: %s", key, exc)


def is_available() -> bool:
    """True iff the ``watchdog`` package is importable."""
    return _HAS_WATCHDOG


def start_event_watcher(
    folder: Path,
    on_new_file: Callable[[Path], None],
    stop: threading.Event,
) -> tuple[threading.Thread, threading.Thread] | None:
    """Start a watchdog observer on ``folder`` (recursive).

    Args:
        folder: Directory to watch.
        on_new_file: Callback fired once per stable file. Runs on the
            pump thread (not the main thread) — keep it short and
            non-blocking; queue the work and let the index worker drain it.
        stop: Threading event the caller can set to request shutdown.
            The returned threads will exit when this is set.

    Returns:
        ``(observer_thread, pump_thread)`` if watchdog is available,
        otherwise ``None`` so the caller can fall back to the polling
        watcher in :mod:`golem.watcher`.
    """
    if not _HAS_WATCHDOG or FileSystemEventHandler is None or Observer is None:
        return None
    try:
        handler = _StableHandler(on_new_file, stop)
        observer = Observer()
        observer.schedule(handler, str(folder), recursive=True)
        observer.start()
    except Exception as exc:  # pragma: no cover
        _LOG.warning("watchdog Observer.start() failed: %s", exc)
        return None

    observer_thread = threading.Thread(
        target=observer.join,
        daemon=True,
        name="golem-watchdog-observer",
    )
    observer_thread._golem_observer = observer
    observer_thread._golem_stop = stop
    observer_thread.start()
    return observer_thread, handler._pump
