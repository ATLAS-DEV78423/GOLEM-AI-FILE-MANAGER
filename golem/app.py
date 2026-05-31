from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from contextlib import contextmanager, closing
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

from .config import AppConfig
from .constants import default_data_dir
from .legal import TERMS_VERSION
from .indexer import connect, ensure_db_file, get_settings, initialize, save_settings
from .search import search_with_fallback
from .scanner import scan_folder
from .summarizer import build_summarizer
from .ui import DesktopApp
from .undo import undo_last
from .tray import TrayCallbacks, TrayController
from .watcher import PollingWatcher


def configure_logging() -> None:
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "golem.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


@dataclass
class AppState:
    config: AppConfig
    db_path: Path
    vault_folder: Path
    watched_folder: Path


class GolemApplication:
    def __init__(self):
        self.data_dir = default_data_dir()
        self.db_path = ensure_db_file(self.data_dir)
        with closing(initialize(self.db_path)) as conn:
            self.config = AppConfig.from_settings(get_settings(conn))
            save_settings(conn, self.config.as_settings())
            conn.commit()
        self.summarizer = build_summarizer(self.config.llm_provider, self.config.llm_api_key, self.config.llm_model, self.config.llm_base_url)
        self.command_queue: Queue[dict] = Queue()
        self.result_queue: Queue[dict] = Queue()
        self.progress_queue: Queue[dict] = Queue()
        self.ui = DesktopApp(self._search, self._open_file, self._reveal_in_explorer, self.save_config)
        self.watcher: PollingWatcher | None = None
        self._watcher_thread: threading.Thread | None = None
        self._hotkey_listener = None
        self._scan_lock = threading.Lock()
        self._undo_lock = threading.Lock()
        self.tray = TrayController(
            TrayCallbacks(
                on_search=lambda: self.enqueue({"action": "show_popup"}),
                on_rescan=lambda: self.enqueue({"action": "scan"}),
                on_toggle_dry_run=lambda: self.enqueue({"action": "toggle_dry_run"}),
                on_undo=lambda: self.enqueue({"action": "undo"}),
                on_settings=lambda: self.enqueue({"action": "settings"}),
                on_quit=lambda: self.enqueue({"action": "quit"}),
            )
        )
        self.ui.root.after(100, self._pump_commands)
        self.ui.root.after(250, self._pump_progress)

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
            self.ui.set_status(f"{latest.get('current_file', '')} - {latest.get('progress', 0.0):.0%}")
        self.ui.root.after(250, self._pump_progress)

    def _scan(self) -> None:
        try:
            watched = Path(self.config.watched_folder)
            vault = Path(self.config.vault_folder)
            watched.mkdir(parents=True, exist_ok=True)
            vault.mkdir(parents=True, exist_ok=True)
            logging.info("Scanning %s", watched)
            with self._connection() as conn:
                scan_folder(
                    conn,
                    watched,
                    vault,
                    self.summarizer,
                    progress=lambda p, current: self.progress_queue.put({"progress": p, "current_file": current}),
                    log=logging.info,
                    dry_run=self.config.dry_run,
                )
        finally:
            self._scan_lock.release()

    def _undo(self) -> None:
        try:
            with self._connection() as conn:
                result = undo_last(conn, Path(self.config.vault_folder))
            logging.info("Undo result: %s", result)
        finally:
            self._undo_lock.release()

    def _search(self, query: str) -> list[dict]:
        if not query.strip():
            return []
        with self._connection() as conn:
            return search_with_fallback(conn, query, self.summarizer, self.config.confidence_threshold)

    def _open_file(self, path: str) -> None:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _reveal_in_explorer(self, path: str) -> None:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])

    def start_watcher(self) -> None:
        if not self.config.watch_enabled or not self.config.watched_folder:
            return
        if self.watcher is not None:
            return
        watched = Path(self.config.watched_folder)
        watched.mkdir(parents=True, exist_ok=True)
        self.watcher = PollingWatcher(watched, self._handle_watcher_event)
        self._watcher_thread = self.watcher.start()
        logging.info("Watcher started")

    def restart_watcher(self) -> None:
        self.stop_watcher()
        self.start_watcher()

    def stop_watcher(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
            if self._watcher_thread is not None and self._watcher_thread.is_alive():
                self._watcher_thread.join(timeout=1.0)
            self.watcher = None
            self._watcher_thread = None

    def _handle_watcher_event(self, path: Path) -> None:
        logging.info("New or changed file: %s", path)
        self.enqueue({"action": "scan"})

    def run(self) -> int:
        if not self.ensure_ready():
            self.ui.run()
            return 0
        self.start_watcher()
        self._start_hotkeys()
        self.tray.start()
        self.enqueue({"action": "scan"})
        self.ui.run()
        return 0

    def _start_hotkeys(self) -> None:
        try:
            import keyboard  # type: ignore

            keyboard.add_hotkey("ctrl+space", lambda: self.enqueue({"action": "show_popup"}))
            self._hotkey_listener = keyboard
            logging.info("Registered keyboard hotkey")
            return
        except Exception:
            pass

        try:
            from pynput import keyboard as pynput_keyboard  # type: ignore

            def on_activate():
                self.enqueue({"action": "show_popup"})

            hotkey = pynput_keyboard.GlobalHotKeys({"<ctrl>+<space>": on_activate})
            hotkey.start()
            self._hotkey_listener = hotkey
            logging.info("Registered pynput hotkey")
        except Exception as exc:
            logging.info("Hotkey registration unavailable: %s", exc)


def run() -> int:
    configure_logging()
    app = GolemApplication()
    return app.run()
