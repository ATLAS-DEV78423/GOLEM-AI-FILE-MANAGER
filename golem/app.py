from __future__ import annotations

import logging
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, closing
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

from .config import AppConfig
from .constants import APP_NAME, default_data_dir
from .legal import TERMS_VERSION
from .indexer import connect, ensure_db_file, get_settings, initialize, save_settings, transaction
from .search import search_with_fallback
from .scanner import scan_folder
from .summarizer import build_summarizer
from .ui import DesktopApp
from .undo import undo_last
from .tray import TrayCallbacks, TrayController
from .watcher import PollingWatcher


_RELEASES_URL = "https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging.

    Writes to ``<data_dir>/golem.log`` and to stdout. Replaces any
    previously installed handlers (so calling this twice in a test
    does not duplicate output).
    """
    data_dir = default_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        log_path = data_dir / "golem.log"
    except OSError:
        # We have nowhere to log; degrade to stderr-only.
        log_path = None

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    if log_path is not None:
        try:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            pass
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    try:
        root.setLevel(getattr(logging, level.upper()))
    except AttributeError:
        root.setLevel(logging.INFO)


@dataclass
class AppState:
    config: AppConfig
    db_path: Path
    vault_folder: Path
    watched_folder: Path


class GolemApplication:
    def __init__(self, dry_run_override: bool | None = None):
        self.data_dir = default_data_dir()
        self.db_path = ensure_db_file(self.data_dir)
        with closing(initialize(self.db_path)) as conn:
            self.config = AppConfig.from_settings(get_settings(conn))
            save_settings(conn, self.config.as_settings())
            conn.commit()
        if dry_run_override is not None:
            self.config.dry_run = dry_run_override
        self.summarizer = build_summarizer(self.config.llm_provider, self.config.llm_api_key, self.config.llm_model, self.config.llm_base_url)
        self.command_queue: Queue[dict] = Queue()
        self.result_queue: Queue[dict] = Queue()
        self.progress_queue: Queue[dict] = Queue()
        # Index events from the watcher are serialized through a single
        # worker thread. The previous design spawned one thread per event,
        # which under load (e.g. dragging 100 files into the watched folder)
        # produced dozens of threads racing for the SQLite WAL lock.
        self.index_queue: Queue[Path] = Queue()
        self._index_stop = threading.Event()
        self.ui = DesktopApp(self._search, self._open_file, self._reveal_in_explorer, self.save_config)
        self.watcher: PollingWatcher | None = None
        self._watcher_thread: threading.Thread | None = None
        self._hotkey_listener: object | None = None
        self._scan_lock = threading.Lock()
        self._undo_lock = threading.Lock()
        self.tray = TrayController(
            TrayCallbacks(
                on_search=lambda: self.enqueue({"action": "show_popup"}),
                on_rescan=lambda: self.enqueue({"action": "scan"}),
                on_toggle_dry_run=lambda: self.enqueue({"action": "toggle_dry_run"}),
                on_undo=lambda: self.enqueue({"action": "undo"}),
                on_settings=lambda: self.enqueue({"action": "settings"}),
                on_open_data_folder=lambda: self._open_path(self.data_dir),
                on_view_log=lambda: self._open_path(self.data_dir / "golem.log"),
                on_reset=lambda: self._confirm_reset(),
                on_check_updates=lambda: self._open_path(_RELEASES_URL),
                on_toggle_watcher=lambda: self._toggle_watcher(),
                on_quit=lambda: self.enqueue({"action": "quit"}),
            )
        )
        self.error_queue: Queue[str] = Queue()
        # Wall-clock time (from time.monotonic) until which the status bar
        # is "owned" by the error pump. The progress pump will not clobber
        # it during this window. 0.0 means "no error in flight".
        self._status_error_until: float = 0.0
        self._index_worker = threading.Thread(target=self._index_worker_loop, name="golem-index-worker", daemon=True)
        self._index_worker.start()
        self.ui.root.after(100, self._pump_commands)
        self.ui.root.after(250, self._pump_progress)
        self.ui.root.after(500, self._pump_errors)

    @contextmanager
    def _connection(self):
        with closing(connect(self.db_path)) as conn:
            yield conn

    def ensure_ready(self) -> bool:
        if self.config.terms_version != TERMS_VERSION or not self.config.terms_accepted or not self.config.watched_folder or not self.config.vault_folder:
            self.ui.show_onboarding()
            return False
        return True

    def save_config(self, watched: str, vault: str, provider: str, api_key: str, model: str, base_url: str, terms_accepted: bool) -> None:
        if not terms_accepted:
            raise ValueError("You must accept the Terms of Service to continue.")
        self.config.watched_folder = watched
        self.config.vault_folder = vault
        self.config.llm_provider = provider
        self.config.llm_api_key = api_key
        self.config.llm_model = model
        self.config.llm_base_url = base_url
        self.config.terms_accepted = True
        self.config.terms_version = TERMS_VERSION
        self.summarizer = build_summarizer(provider, api_key, model, base_url)
        with self._connection() as conn:
            save_settings(conn, self.config.as_settings())
            conn.commit()
        self.ui.set_status("Settings saved")
        self.restart_watcher()
        self.enqueue({"action": "scan"})

    def enqueue(self, command: dict) -> None:
        self.command_queue.put(command)

    def _pump_commands(self) -> None:
        while not self.command_queue.empty():
            command = self.command_queue.get_nowait()
            try:
                action = command.get("action")
                if action == "scan":
                    if self._scan_lock.acquire(blocking=False):
                        threading.Thread(target=self._scan, daemon=True).start()
                    else:
                        logging.info("Scan already running; skipping duplicate request")
                elif action == "undo":
                    if self._undo_lock.acquire(blocking=False):
                        threading.Thread(target=self._undo, daemon=True).start()
                    else:
                        logging.info("Undo already running; skipping duplicate request")
                elif action == "index_file":
                    path_str = command.get("path", "")
                    if path_str:
                        self.enqueue_index(Path(path_str))
                elif action == "watch":
                    self.start_watcher()
                elif action == "show_popup":
                    self.ui.show_popup()
                elif action == "open":
                    self._open_file(command["path"])
                elif action == "reveal":
                    self._reveal_in_explorer(command["path"])
                elif action == "toggle_dry_run":
                    self.config.dry_run = not self.config.dry_run
                    with self._connection() as conn:
                        save_settings(conn, self.config.as_settings())
                        conn.commit()
                    logging.info("Dry-run set to %s", self.config.dry_run)
                elif action == "settings":
                    self.ui.show_onboarding()
                elif action == "reset":
                    self._reset_all()
                elif action == "quit":
                    self.stop_watcher()
                    self.tray.stop()
                    self.ui.root.quit()
            except Exception as exc:
                logging.exception("Command failed: %s", exc)
        self.ui.root.after(100, self._pump_commands)

    def _pump_progress(self) -> None:
        latest = None
        while not self.progress_queue.empty():
            latest = self.progress_queue.get_nowait()
        if latest:
            # The progress pump only updates the status bar if no error
            # is currently being shown. Errors are higher-priority; a
            # one-off progress tick would otherwise clobber a "⚠ ..."
            # message that the user is still trying to read.
            if not self._status_error_until or self._status_error_until < time.monotonic():
                self.ui.set_status(f"{latest.get('current_file', '')} - {latest.get('progress', 0.0):.0%}")
        self.ui.root.after(250, self._pump_progress)

    def _pump_errors(self) -> None:
        """Surface user-facing error messages on the status bar.

        Background threads (scanner, watcher, index worker) post short
        messages here when they hit a recoverable error. The pump runs
        on the UI thread so it can update widgets safely. An error
        message is shown for ``_ERROR_DISPLAY_SECONDS`` seconds and the
        progress pump respects that window.
        """
        try:
            message = self.error_queue.get_nowait()
        except queue.Empty:
            message = None
        if message:
            self._status_error_until = time.monotonic() + self._ERROR_DISPLAY_SECONDS
            self.ui.set_status(f"⚠ {message}")
            # Schedule a clear so the status doesn't stay on the error
            # forever if no further errors arrive.
            self.ui.root.after(
                int(self._ERROR_DISPLAY_SECONDS * 1000), self._clear_error_status
            )
        self.ui.root.after(500, self._pump_errors)

    _ERROR_DISPLAY_SECONDS = 6.0

    def _clear_error_status(self) -> None:
        """Clear the error banner if it is still the one we set.

        Cheap: we just re-set the status to the empty string. The next
        progress tick (if any) will replace it.
        """
        try:
            self.ui.set_status("")
        except Exception:
            pass
        self._status_error_until = 0.0

    def _reset_all(self) -> None:
        """Wipe settings, files index, and undo log, then restart onboarding.

        The database file is left in place (it is cheaper to DELETE rows
        than to drop and re-create the schema). After the wipe we ask
        the user to re-onboard.
        """
        with self._connection() as conn:
            with transaction(conn):
                conn.execute("DELETE FROM settings")
                conn.execute("DELETE FROM files")
                conn.execute("DELETE FROM files_fts")
                conn.execute("DELETE FROM undo_log")
        self.config = AppConfig()  # back to defaults
        logging.info("All settings and index wiped; restarting onboarding")
        self.ui.show_onboarding()

    def _scan(self) -> None:
        try:
            self.tray.set_busy(True)
            watched = Path(self.config.watched_folder)
            vault = Path(self.config.vault_folder)
            watched.mkdir(parents=True, exist_ok=True)
            vault.mkdir(parents=True, exist_ok=True)
            logging.info("Scanning %s", watched)
            with self._connection() as conn:
                result = scan_folder(
                    conn,
                    watched,
                    vault,
                    self.summarizer,
                    progress=lambda p, current: self.progress_queue.put({"progress": p, "current_file": current}),
                    log=logging.info,
                    dry_run=self.config.dry_run,
                )
            logging.info(
                "Scan complete: %d processed, %d skipped, %d errors",
                result.processed, result.skipped, result.errors,
            )
            self.tray.notify(
                "GOLEM scan complete",
                f"Indexed {result.processed} file(s), skipped {result.skipped}, errors {result.errors}.",
            )
        finally:
            self.tray.set_busy(False)
            self._scan_lock.release()

    def _undo(self) -> None:
        try:
            with self._connection() as conn:
                result = undo_last(conn, Path(self.config.vault_folder))
            logging.info("Undo result: %s", result)
        finally:
            self._undo_lock.release()

    def _index_single(self, path: Path) -> None:
        try:
            watched = Path(self.config.watched_folder)
            vault = Path(self.config.vault_folder)
            try:
                path.resolve().relative_to(watched.resolve())
            except ValueError:
                return
            with self._connection() as conn:
                from .scanner import index_one_file
                index_one_file(conn, path, vault, self.summarizer, dry_run=self.config.dry_run, log=logging.info)
        except Exception as exc:
            logging.exception("Watcher index error for %s: %s", path, exc)

    def enqueue_index(self, path: Path) -> None:
        """Queue a path for the dedicated index worker.

        Prefer this over calling ``_index_single`` directly; the watcher
        may produce many events in a burst and we serialize them through
        a single worker so SQLite WAL contention is bounded.
        """
        try:
            self.index_queue.put_nowait(path)
        except queue.Full:
            logging.warning("Index queue full; dropping %s", path)

    def _index_worker_loop(self) -> None:
        """Single dedicated worker that drains the index queue.

        Replaces the per-event thread spawn in the previous implementation.
        One connection per index keeps WAL contention to a single writer.
        A ``None`` sentinel in the queue means "exit cleanly".
        """
        while True:
            try:
                path = self.index_queue.get(timeout=0.5)
            except queue.Empty:
                if self._index_stop.is_set():
                    return
                continue
            if path is None:
                self.index_queue.task_done()
                return
            try:
                self._index_single(path)
            except Exception as exc:
                logging.exception("Index worker failed for %s: %s", path, exc)
            finally:
                self.index_queue.task_done()

    def _search(self, query: str) -> dict:
        if not query.strip():
            return {"status": "ok", "results": [], "message": ""}
        with self._connection() as conn:
            return search_with_fallback(conn, query, self.summarizer, self.config.confidence_threshold).to_payload()

    def _open_file(self, path: str) -> None:
        self._open_path(Path(path))

    def _open_path(self, path: Path | str) -> None:
        """Open a file or URL with the OS's default handler.

        Used by the tray menu to open the data folder, the log file, the
        GitHub releases page, etc. Errors are logged and silently dropped
        — opening a folder is a convenience, not a critical operation.
        """
        try:
            target = str(path)
            if sys.platform.startswith("win"):
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except OSError as exc:
            logging.warning("Could not open %s: %s", path, exc)

    def _reveal_in_explorer(self, path: str) -> None:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])

    def _confirm_reset(self) -> None:
        """Ask the user to confirm wiping all settings + index.

        Implemented as a deferred command so the actual wipe runs on
        the UI thread (where the dialog can be displayed) and the
        command_queue (which is drained on the UI thread) can handle
        the cascading actions.
        """
        from tkinter import messagebox

        ok = messagebox.askyesno(
            "GOLEM",
            "Reset all settings and clear the local index?\n\n"
            "This will wipe:\n"
            "  - Your saved API key\n"
            "  - The watched folder and vault paths\n"
            "  - The full local index (every note and tag)\n"
            "  - The undo log (you will not be able to undo recent moves)\n\n"
            "Your files in the Obsidian vault and the watched folder are not "
            "deleted. You will need to re-enter the watched folder, vault, and "
            "API key on next launch.",
        )
        if not ok:
            return
        self.enqueue({"action": "reset"})

    def _toggle_watcher(self) -> None:
        self.config.watch_enabled = not self.config.watch_enabled
        with self._connection() as conn:
            save_settings(conn, self.config.as_settings())
            conn.commit()
        if self.config.watch_enabled:
            self.start_watcher()
            logging.info("Watcher enabled")
        else:
            self.stop_watcher()
            logging.info("Watcher disabled")

    def start_watcher(self) -> None:
        if not self.config.watch_enabled or not self.config.watched_folder:
            return
        if self.watcher is not None:
            return
        watched = Path(self.config.watched_folder)
        watched.mkdir(parents=True, exist_ok=True)
        self.watcher = PollingWatcher(watched, self._handle_watcher_event)
        # start() returns a tuple (poll_thread, worker_thread); the worker
        # is the one that processes events, so it's the one we wait on.
        _poll_thread, worker_thread = self.watcher.start()
        self._watcher_thread = worker_thread
        logging.info("Watcher started")

    def restart_watcher(self) -> None:
        self.stop_watcher()
        self.start_watcher()

    def stop_watcher(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
            self._watcher_thread = None

    def _handle_watcher_event(self, path: Path) -> None:
        self.enqueue({"action": "index_file", "path": str(path)})

    def shutdown(self) -> None:
        """Stop the watcher, the index worker, and the tray.

        Called from the quit path. Idempotent.
        """
        self._index_stop.set()
        # Best-effort wake the worker in case it's blocked on get(timeout=...).
        try:
            self.index_queue.put_nowait(None)  # type: ignore[arg-type]
        except queue.Full:
            pass
        self.stop_watcher()
        self.tray.stop()

    def run(self) -> int:
        if not self.ensure_ready():
            self.ui.run()
            self.shutdown()
            return 0
        self.start_watcher()
        self._start_hotkeys()
        self.tray.start()
        self.enqueue({"action": "scan"})
        try:
            self.ui.run()
        finally:
            self.shutdown()
        return 0

    def _start_hotkeys(self) -> None:
        if self._hotkey_listener == "disabled":
            logging.info("Hotkeys disabled by CLI flag")
            return
        try:
            import keyboard

            keyboard.add_hotkey("ctrl+shift+space", lambda: self.enqueue({"action": "show_popup"}))
            self._hotkey_listener = keyboard
            logging.info("Registered keyboard hotkey (ctrl+shift+space)")
            return
        except Exception:
            pass

        try:
            from pynput import keyboard as pynput_keyboard

            def on_activate():
                self.enqueue({"action": "show_popup"})

            hotkey = pynput_keyboard.GlobalHotKeys({"<ctrl>+<shift>+<space>": on_activate})
            hotkey.start()
            self._hotkey_listener = hotkey
            logging.info("Registered pynput hotkey (ctrl+shift+space)")
        except Exception as exc:
            logging.info("Hotkey registration unavailable: %s", exc)


def _show_fatal_error(message: str) -> None:
    """Display a tkinter error dialog.

    Used when the application fails to start, before the main window exists.
    Falls back to a stderr message if tkinter is unavailable (e.g. running
    under a headless test runner).
    """
    logging.exception("Fatal startup error: %s", message)
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        root = _tk.Tk()
        root.withdraw()
        _mb.showerror(APP_NAME, f"{APP_NAME} could not start.\n\n{message}\n\nSee the log file for details.")
        root.destroy()
    except Exception:
        # Last-ditch: stderr is the best we can do.
        print(f"FATAL: {APP_NAME} could not start: {message}", file=sys.stderr)


def _version_string() -> str:
    from .constants import APP_NAME, APP_VERSION
    return f"{APP_NAME} {APP_VERSION}"


def _export_db(db_path: Path, dest: Path) -> int:
    """Copy the SQLite database to ``dest`` and exit.

    Used by ``--export-db``. The destination parent must exist.
    """
    import shutil
    if not db_path.is_file():
        print(f"Database does not exist yet: {db_path}", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    # VACUUM INTO would be cleaner but requires a writable source dir and
    # leaves a -wal/-shm pair. A binary copy with the WAL flushed first
    # is portable and gives the user a self-contained file.
    with closing(connect(db_path)) as conn:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError as exc:
            print(f"Could not checkpoint WAL: {exc}", file=sys.stderr)
            return 1
    shutil.copy2(db_path, dest)
    print(f"Exported database to {dest}")
    return 0


def _clear_index(db_path: Path) -> int:
    """Wipe the files index (keeping settings and undo log) and exit."""
    if not db_path.is_file():
        return 0
    with closing(connect(db_path)) as conn:
        with transaction(conn):
            conn.execute("DELETE FROM files")
            # FTS5 is auto-cleaned by the AFTER DELETE trigger.
    print("Index cleared. The next scan will rebuild it from scratch.")
    return 0


def run(args: object | None = None) -> int:
    """GOLEM entry point.

    Accepts an optional argparse Namespace (``main.py``) or no arguments
    (legacy callers). When CLI flags are supplied they override the
    saved config where applicable.
    """
    log_level = "INFO"
    no_tray = False
    no_watcher = False
    no_hotkey = False
    dry_run_override: bool | None = None
    do_reindex = False
    export_path: Path | None = None
    show_version = False

    if args is not None:
        log_level = getattr(args, "log_level", "INFO")
        no_tray = getattr(args, "no_tray", False)
        no_watcher = getattr(args, "no_watcher", False)
        no_hotkey = getattr(args, "no_hotkey", False)
        if getattr(args, "dry_run", False):
            dry_run_override = True
        do_reindex = getattr(args, "reindex", False)
        export_path_raw = getattr(args, "export_db", None)
        if export_path_raw:
            export_path = Path(export_path_raw)
        show_version = getattr(args, "version", False)

    if show_version:
        print(_version_string())
        return 0

    configure_logging(level=log_level)

    db_path = ensure_db_file(default_data_dir())

    if export_path is not None:
        return _export_db(db_path, export_path)

    if do_reindex:
        rc = _clear_index(db_path)
        if rc != 0:
            return rc

    try:
        app = GolemApplication(dry_run_override=dry_run_override)
    except Exception as exc:
        _show_fatal_error(str(exc))
        return 1

    # Wire the CLI flag overrides.
    if no_tray:
        app.tray.disable()
    if no_watcher:
        app.config.watch_enabled = False
    if no_hotkey:
        app._hotkey_listener = "disabled"

    try:
        return app.run()
    except Exception as exc:
        _show_fatal_error(str(exc))
        return 1
