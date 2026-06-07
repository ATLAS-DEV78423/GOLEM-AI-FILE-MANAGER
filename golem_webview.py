"""
GOLEM WebView Launcher — PyWebView front-end for the GOLEM backend.

Replaces the Tkinter-based DesktopApp with a frameless HTML/CSS/JS window
powered by pywebview. The UI lives in the ``ui/`` directory and communicates
with Python through ``window.pywebview.api.*``.

Usage::

    python golem_webview.py

Keyboard::

    Ctrl+Space       — toggle launcher (Windows/Linux)
    Cmd+Shift+Space  — toggle launcher (macOS, to avoid Spotlight conflict)
    ↑↓               — navigate results
    Enter            — open selected file
    Cmd/Ctrl+Enter   — reveal selected file in file manager
    Escape           — close launcher
    Tab              — cycle type filters
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import webview

# ── GOLEM backend imports ──────────────────────────────────────────
try:
    from golem.ai import CachedSummarizer
    from golem.config import AppConfig
    from golem.constants import APP_NAME, APP_VERSION, default_data_dir
    from golem.indexer import (
        connect,
        ensure_db_file,
        get_settings,
        initialize,
        save_settings,
    )
    from golem.scanner import index_one_file, scan_folder
    from golem.search import search_with_fallback
    from golem.summarizer import build_summarizer
    from golem.watcher import PollingWatcher
except ImportError as exc:
    print(f"ERROR: Could not import GOLEM backend: {exc}")
    print("Make sure the golem package is installed or in the Python path.")
    sys.exit(1)

_LOG = logging.getLogger(__name__)

# ── Window reference (set after webview.create_window) ─────────────
_window: webview.Window | None = None


# ─── File type helpers ─────────────────────────────────────────────
def _file_type_from_name(filename: str) -> str:
    """Guess a semantic file type from a filename."""
    if not filename:
        return "unknown"
    _, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
    ext = ext.lower()
    mapping: dict[str, str] = {
        "pdf": "pdf", "doc": "docx", "docx": "docx", "xls": "xlsx", "xlsx": "xlsx",
        "csv": "csv", "md": "md", "txt": "txt",
        "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
        "svg": "image", "webp": "image",
        "mp4": "video", "mov": "video", "avi": "video", "mkv": "video", "webm": "video",
        "mp3": "audio", "wav": "audio", "flac": "audio", "m4a": "audio",
        "py": "code", "js": "code", "ts": "code", "jsx": "code", "tsx": "code",
        "html": "code", "css": "code", "json": "code", "yaml": "code", "yml": "code",
        "zip": "archive", "rar": "archive", "tar": "archive", "gz": "archive",
        "ppt": "presentation", "pptx": "presentation",
    }
    return mapping.get(ext, "unknown")


def _format_modified(modified: str | None) -> str:
    """Format a modified timestamp for the UI."""
    if not modified:
        return ""
    if "ago" in modified or "just now" in modified:
        return modified
    return modified


# ─── GolemAPI — exposed to JavaScript ─────────────────────────────
class GolemAPI:
    """Exposed to JavaScript via ``window.pywebview.api``."""

    def __init__(
        self,
        db_path: Path,
        summarizer: CachedSummarizer,
        config: AppConfig,
    ):
        self._db_path = db_path
        self._summarizer = summarizer
        self._config = config
        self._connection_lock = threading.Lock()
        self._watcher: PollingWatcher | None = None
        self._status: dict[str, Any] = {
            "file_count": 0,
            "status": "ready",
            "message": "",
        }

    def _get_conn(self):
        """Open a fresh connection for each request."""
        conn = connect(self._db_path)
        conn.execute("PRAGMA query_only = 1")
        return conn

    # ── Start watcher ──────────────────────────────────────────────

    def start_watcher(self) -> None:
        """Start the polling watcher for the configured watched folder."""
        if self._watcher is not None or not self._config.watched_folder:
            return
        watched = Path(self._config.watched_folder)
        if not watched.exists():
            return
        self._watcher = PollingWatcher(
            watched,
            on_new_file=self._handle_watcher_event,
            interval=3.0,
            debounce_seconds=2.0,
        )
        self._watcher.start()
        _LOG.info("Watcher started for %s", watched)

    def stop_watcher(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
            _LOG.info("Watcher stopped")

    def _handle_watcher_event(self, path: Path) -> None:
        """Handle a new or modified file from the watcher."""
        try:
            vault = Path(self._config.vault_folder)
            with self._connection_lock, closing(connect(self._db_path)) as conn:
                index_one_file(conn, path, vault, self._summarizer, dry_run=self._config.dry_run)
            _LOG.debug("Indexed watcher event: %s", path)
        except Exception as exc:
            _LOG.warning("Watcher index failed for %s: %s", path, exc)

    # ── Trigger full scan ──────────────────────────────────────────

    def trigger_scan(self) -> None:
        """Run a full scan in a background thread."""
        def _scan():
            try:
                self._status["status"] = "indexing"
                watched = Path(self._config.watched_folder)
                vault = Path(self._config.vault_folder)
                with self._connection_lock, closing(connect(self._db_path)) as conn:
                    scan_folder(conn, watched, vault, self._summarizer)
                self._status["status"] = "ready"
                self._update_file_count()
            except Exception as exc:
                _LOG.exception("Scan failed: %s", exc)
                self._status["status"] = "error"
                self._status["message"] = str(exc)

        threading.Thread(target=_scan, daemon=True, name="golem-scan").start()

    # ── Search ─────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        """Search the index and return results for the front-end.

        Returns::

            [{
                "file_name": str, "file_path": str, "file_type": str,
                "snippet": str, "match_type": str,
                "matched_terms": list[str], "modified_at": str, "group": str
            }]
        """
        if not query or not query.strip():
            return []

        _LOG.info("Search: %s (top_k=%d)", query[:80], top_k)

        try:
            with self._connection_lock, closing(self._get_conn()) as conn:
                response = search_with_fallback(
                    conn,
                    query,
                    self._summarizer,
                    self._config.confidence_threshold,
                )
        except Exception as exc:
            _LOG.exception("Search failed: %s", exc)
            return []

        payload = response.to_payload()
        raw_results = payload.get("results", [])

        if not raw_results:
            return []

        out: list[dict[str, Any]] = []
        for r in raw_results[:top_k]:
            file_name = str(r.get("clean_filename") or r.get("original_filename") or "")
            file_path = str(r.get("current_path") or r.get("original_path") or "")
            file_type = _file_type_from_name(file_name)
            snippet = str(r.get("chunk_text") or r.get("summary") or "")
            match_type = str(r.get("match_type") or "")
            matched_terms = r.get("matched_terms", [])
            modified_at = str(r.get("modified_at") or "")
            category = str(r.get("category") or "")
            confidence = float(r.get("confidence", 0.0) or 0.0)

            if confidence >= 0.9:
                group = "TOP MATCHES"
            elif category:
                group = category.upper()
            else:
                group = "ALSO RELATED"

            # Extract graph neighbor data (tags, categories, related files)
            related = r.get("related", [])
            related_tags = [
                x["label"] for x in related if x.get("type") == "tag"
            ][:3]
            related_files = [
                x["label"] for x in related if x.get("type") == "related_file"
            ][:2]
            related_categories = [
                x["label"] for x in related if x.get("type") == "project"
            ][:1]

            out.append({
                "file_name": file_name,
                "file_path": file_path,
                "file_type": file_type,
                "snippet": snippet[:200],
                "match_type": match_type,
                "matched_terms": matched_terms or [],
                "modified_at": _format_modified(modified_at),
                "group": group,
                "related_tags": related_tags,
                "related_files": related_files,
                "related_categories": related_categories,
            })

        return out

    # ── File operations ────────────────────────────────────────────

    def open_file(self, path: str) -> None:
        """Open a file with the OS default application."""
        if not path or not path.strip():
            return
        _LOG.info("Open file: %s", path)
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            elif platform.system() == "Windows":
                os.startfile(path)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            _LOG.exception("Failed to open %s: %s", path, exc)

    def reveal_in_finder(self, path: str) -> None:
        """Reveal a file in the OS file manager."""
        if not path or not path.strip():
            return
        _LOG.info("Reveal file: %s", path)
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", path])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select,", path])
            else:
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
        except Exception as exc:
            _LOG.exception("Failed to reveal %s: %s", path, exc)

    def hide_window(self) -> None:
        """Hide the launcher window."""
        global _window
        _LOG.debug("Hide window")
        if _window is not None:
            try:
                _window.hide()
            except Exception:
                pass

    def show_window(self) -> None:
        """Show and focus the launcher window."""
        global _window
        if _window is not None:
            try:
                _window.show()
                _window.evaluate_js(
                    "document.getElementById('searchInput').focus();"
                    "document.getElementById('searchInput').select();"
                )
            except Exception:
                pass

    # ── Status ─────────────────────────────────────────────────────

    def _update_file_count(self) -> None:
        """Query the DB for current file count."""
        try:
            with self._connection_lock, closing(self._get_conn()) as conn:
                row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
                self._status["file_count"] = row[0] if row else 0
        except Exception:
            pass

    def get_status(self) -> dict[str, Any]:
        """Return current status (file count, indexing state)."""
        self._update_file_count()
        return dict(self._status)


# ─── Entry point ───────────────────────────────────────────────────
def _configure_logging(data_dir: Path) -> None:
    """Set up basic logging to file and stdout."""
    log_path = data_dir / "golem_webview.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _toggle_window(api: GolemAPI) -> None:
    """Show or hide the launcher window (called from hotkey)."""
    global _window
    if _window is None:
        return
    try:
        if _window.hidden:
            api.show_window()
        else:
            api.hide_window()
    except Exception as exc:
        _LOG.warning("Toggle window failed: %s", exc)


def _register_hotkeys(api: GolemAPI) -> None:
    """Register global hotkeys in a background thread."""
    try:
        import keyboard as kb

        if platform.system() == "Darwin":
            hotkey = "cmd+shift+space"
        else:
            hotkey = "ctrl+space"

        kb.add_hotkey(hotkey, lambda: _toggle_window(api), suppress=True)
        _LOG.info("Registered hotkey: %s", hotkey)
        kb.wait()
    except ImportError:
        _LOG.warning("keyboard module not installed. Install with: pip install keyboard")
    except Exception as exc:
        _LOG.warning("Hotkey registration failed: %s", exc)


def _periodic_status(api: GolemAPI, interval: float = 30.0) -> None:
    """Periodically update the file count in a background thread."""
    while True:
        try:
            api._update_file_count()
        except Exception:
            pass
        time.sleep(interval)


def main() -> int:
    """GOLEM WebView launcher entry point."""
    # ── Data directory & DB ───────────────────────────────────────
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(data_dir)

    _LOG.info("Starting %s %s (WebView)", APP_NAME, APP_VERSION)
    _LOG.info("Data directory: %s", data_dir)

    db_path = ensure_db_file(data_dir)

    # ── Config ────────────────────────────────────────────────────
    with closing(initialize(db_path)) as conn:
        settings = get_settings(conn)
        config = AppConfig.from_settings(settings)
        save_settings(conn, config.as_settings())
        conn.commit()

    _LOG.info("Config loaded: provider=%s, model=%s", config.llm_provider, config.llm_model)

    # If no watched folder configured, try to use the default
    if not config.watched_folder:
        default_watched = data_dir / "GOLEM Files"
        default_watched.mkdir(parents=True, exist_ok=True)
        config.watched_folder = str(default_watched)
        with closing(connect(db_path)) as conn:
            save_settings(conn, config.as_settings())

    if not config.vault_folder:
        default_vault = data_dir / "GOLEM Vault"
        default_vault.mkdir(parents=True, exist_ok=True)
        config.vault_folder = str(default_vault)
        with closing(connect(db_path)) as conn:
            save_settings(conn, config.as_settings())

    # ── Summarizer ────────────────────────────────────────────────
    raw_summarizer = build_summarizer(
        config.llm_provider,
        config.llm_api_key,
        config.llm_model,
        config.llm_base_url,
    )
    summarizer = CachedSummarizer(raw_summarizer, db_path)

    # ── API ───────────────────────────────────────────────────────
    api = GolemAPI(db_path, summarizer, config)

    # ── HTML entry ────────────────────────────────────────────────
    ui_dir = Path(__file__).resolve().parent / "ui"
    index_path = ui_dir / "index.html"

    if not index_path.is_file():
        _LOG.error("UI file not found at %s. Make sure the ui/ directory exists.", index_path)
        return 1

    _LOG.info("UI path: %s", index_path)

    # ── PyWebView window ──────────────────────────────────────────
    global _window
    _window = webview.create_window(
        title="GOLEM",
        url=str(index_path),
        js_api=api,
        width=620,
        height=580,
        min_size=(620, 400),
        resizable=False,
        frameless=True,
        transparent=True,
        on_top=True,
        background_color="#00000000",
        easy_drag=False,
    )

    # ── Start watcher + background tasks ──────────────────────────
    api.start_watcher()

    # Periodic status updates
    status_thread = threading.Thread(
        target=_periodic_status, args=(api, 30.0),
        daemon=True, name="golem-status",
    )
    status_thread.start()

    # Background scan if files exist in watched folder
    initial_count = api.get_status().get("file_count", 0)
    if initial_count == 0:
        watched = Path(config.watched_folder)
        if watched.exists() and any(watched.iterdir()):
            _LOG.info("No indexed files found; triggering initial scan")
            api.trigger_scan()
    else:
        _LOG.info("Resuming with %d indexed files", initial_count)

    # ── Start hotkey listener ─────────────────────────────────────
    hotkey_thread = threading.Thread(
        target=_register_hotkeys, args=(api,),
        daemon=True, name="golem-hotkeys",
    )
    hotkey_thread.start()

    # ── Start the GUI event loop ──────────────────────────────────
    _LOG.info("Starting PyWebView GUI...")
    webview.start(debug=False)

    # Cleanup
    api.stop_watcher()
    _LOG.info("GOLEM WebView stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
