# Changelog

All notable changes to GOLEM are documented in this file. Versions follow
[Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-06-06

### Major — New PyWebView Launcher UI

- **Floating search window** — frameless HTML/CSS/JS launcher powered by PyWebView.
  Replaces the legacy Tkinter popup with a modern dark-themed UI.
- **Outfit + JetBrains Mono** fonts loaded from Google Fonts — no more system font
  fallbacks. The UI now has a premium, designed look.
- **Animations**: 130ms `launchIn` scale+fade on window open, 180ms `itemIn` stagger
  (30ms increments, slide from left), spring `cubic-bezier(0.34,1.56,0.64,1)` on
  icon and pill hover, `scale(0.99)` press on items, `scale(0.94)` press on filter
  pills.
- **Skeleton shimmer loader** — animated gradient rows appear while search runs,
  replaced by results when they arrive. No more blank screen while waiting.
- **Status dot** — pulsing green glow (2.5s) for idle, amber scaling pulse (1.2s)
  for indexing.
- **ESC badge hover** — orange tint on hover for keyboard hints and the ESC badge.
- **Keyboard navigation** — ↑↓ navigate, Enter open, Cmd/Ctrl+Enter reveal in
  Finder/Explorer, Tab cycle filters, Escape close.
- **Type filter pills** — All / Files / Videos / Notes / Audio / Web with active
  state highlighting.
- **Match-type pills** — color-coded `keyword`, `semantic`, `both`, `via entity`
  pills explained.
- **Term highlighting** — matched query terms highlighted in orange in file names
  and snippets.
- **Empty state + idle welcome** — graceful empty state with guidance text, and a
  welcome screen with search icon when the input is empty.

### Enhanced — Graph-Powered Search

- **Deeper graph traversal** — `_enrich_with_graph()` depth increased from 1 to 2
  hops. Search results now surface tags → related files and categories → member
  files, revealing indirect but contextually relevant connections.
- **Graph dedup** — `seen_labels` prevents duplicate tags/files in the related
  list. Related items sorted: tags first → categories → related files.
- **Folder-proximity scoring** — files sharing the same parent directory as the
  top result get a confidence boost (+0.08 for same dir, +0.04 for sibling dir).
  Results re-sorted after boost.
- **Graph chips in UI** — purple `#tag` chips and teal `📎 file` chips shown below
  each result, preserving color distinction when selected.

### New — golem_webview.py Entry Point

- **PyWebView integration** — standalone `golem_webview.py` entry point that wraps
  the GOLEM backend in a frameless, transparent HTML window.
- **GolemAPI class** — exposes `search()`, `open_file()`, `reveal_in_finder()`,
  `hide_window()`, `show_window()`, `get_status()`, `trigger_scan()`,
  `start_watcher()` to JavaScript via `window.pywebview.api.*`.
- **PollingWatcher** — auto-indexes new/modified files in the watched folder.
- **Perodic status** — background thread fetches file count every 30s.
- **Initial scan** — auto-triggers if no indexed files exist on first run.
- **Default folders** — creates `GOLEM Files` and `GOLEM Vault` if none configured.
- **Global hotkey**: `Ctrl+Space` (Windows/Linux) or `Cmd+Shift+Space` (macOS).

### Improved — Installer & Build

- **golem.spec** updated to target `golem_webview.py` (webview) instead of legacy
  `main.py` (Tkinter). Includes `pywebview` and all platform backends in hidden
  imports.
- **golem_webview.spec** added as an alternative PyInstaller spec.
- **pywebview>=6.2.0** added to `requirements.txt` and `pyproject.toml` dependencies.
- **INSTALLATION.md** completely rewritten with step-by-step guides for fresh
  Windows, macOS, and Linux setups — including Python install instructions,
  download links, first-time setup, and troubleshooting tables.
- **Version bumped to 2.1.0**.

### Search & Backend

- **Folder-proximity boost** in `_hybrid_candidates()` — files nearby the top
  result get confidence and RRF score boosts.
- **Graph enrichment depth** increased from 1 to 2 in `_enrich_with_graph()`.
- **Graph data surfaced** through `GolemAPI.search()` — `related_tags`,
  `related_files`, `related_categories` in every result.
- **Type-safe float conversions** in proximity scoring (prevents `float` vs `None`
  comparison).
- **CSS selected state** for graph chips preserves color distinction (purple for
  tags, teal for files) instead of flattening to white.

## [Unreleased]

### Code Quality
- **Type safety**: fixed 40+ mypy errors across the codebase — removed stale
  `type: ignore` comments, added proper type annotations for `_SENTINEL`,
  `SentenceTransformer`, and `check_provider_connection`.
- **Lint**: resolved all ruff violations (S608 SQL injection false positives
  with whitelist validation, S108 test path warnings, duplicate dict keys,
  missing imports).
- **Formatting**: applied `ruff format` to all 57 source files for consistent
  code style.
- **Bug fix**: fixed `checkpoint_wal` in `indexer.py` — SQLite PRAGMA statements
  do not support `?` parameter binding, which caused an integration test
  failure (`test_restore_from_backup_recovers_data`).
- **Bug fix**: removed duplicate `"m4a"` key in `_FILE_TYPE_EMOJI` dict in
  `ui_components.py`.
- **Bug fix**: added missing `Any` import in `app.py` for the `_search_wrapper`
  type signature.

### Security
- **XML parsing**: replaced unsafe `xml.etree.ElementTree` with `defusedxml`
  to prevent XML bomb (Billion Laughs) attacks in Office document extraction.
  Added `defusedxml>=0.7.1` to dependencies and PyInstaller hidden imports.
- **Encryption**: fixed missing `import sys` in `indexer.py` that would cause a
  `NameError` on macOS/Linux when encrypting API keys. Fixed `_unprotect_fernet`
  to catch `base64` decode errors from tampered ciphertext.

### Build
- **Windows installer**: fixed `build_windows_installer.ps1` to set `PYTHONPATH`
  before generating the payload manifest so the `golem` module can be imported.
- **Windows installer**: built `dist/GOLEM-Setup-2.1.0.exe` (67.3 MB) locally.
- **Build validation**: verified all build scripts parse correctly. Mypy is clean
  (0 errors). All 204 tests pass. Ruff is clean.

### Docs
- **Download guides**: added `docs/DOWNLOAD_WINDOWS.md`, `docs/DOWNLOAD_MACOS.md`,
  and `docs/DOWNLOAD_LINUX.md` with per-platform system requirements, install
  options, and troubleshooting.

### Security
- **Installer**: payload source must be inside a build output directory; the
  `GOLEM_PAYLOAD_DIR` env var no longer points to arbitrary folders. Set
  `GOLEM_PAYLOAD_BYPASS_ROOT_CHECK=1` to opt out (trusted callers only).
- **Installer**: `uninstall_app` now refuses to run if there is no
  `install-manifest.json` at the install dir, or if the manifest declares
  a different `app_name`. Shortcut paths declared in the manifest are
  validated against the Start Menu and Desktop roots before unlinking.
- **Settings**: legacy plaintext `groq_api_key` rows are now migrated to
  DPAPI-protected `llm_api_key` on first run. Both keys are listed in
  `SECRET_SETTINGS`.

### Correctness
- **Scanner**: file hashing now uses a full-file SHA-256 for files up to
  10 MB, and a first+last 64 KB hash for larger files. The previous
  first-64 KB-only hash produced false-positive duplicate detections.
- **Utils**: `safe_move` always falls back to copy + unlink on any
  `OSError` from `shutil.move`. The previous errno-based detection
  missed many real cross-volume / network-share failures.
- **Search**: FTS5 query failures are caught and logged; the search
  popup gets an empty result instead of a crash.
- **Search**: rerank path comparison is case-insensitive on Windows /
  macOS and tolerant of `\\` vs `/` separators.
- **Scanner**: `reconcile_missing` streams rows in batches of 500; a
  100 k-row index no longer loads everything into memory.

### Concurrency
- **App**: watch events are now serialized through a single dedicated
  index worker thread, replacing the per-event `threading.Thread`
  spawn that could create dozens of threads competing for the SQLite
  WAL lock under load.

### UX
- **Onboarding**: API keys shorter than 20 characters prompt a
  confirmation before continuing.
- **Hotkey**: default is now `Ctrl+Shift+Space` to avoid the conflict
  with the Windows IME toggle (`Ctrl+Space`).
- **CLI**: `python main.py --help` now lists `--data-dir`, `--log-level`,
  `--no-tray`, `--no-watcher`, `--no-hotkey`, `--dry-run`, `--reindex`,
  `--export-db`, and `--version`.
- **Logging**: log format now includes the module name and a re-entrant
  `configure_logging` so tests do not duplicate handlers.

### Build & release
- **CI**: new `.github/workflows/ci.yml` runs `pytest`, `ruff`, and
  `mypy` on Windows, macOS, and Linux for Python 3.11 and 3.12.
- **Build**: `build_windows_installer.ps1` no longer hard-codes a
  developer-specific Python path. It looks up Python on `PATH` and
  creates a `.venv-build` venv as needed.
- **Build**: `build_macos_installer.sh` uses a project-local venv
  matching the Windows script.
- **Packaging**: `pyproject.toml` declares project metadata, optional
  dependency groups, and entry points. `requirements.txt` is split
  into `requirements-dev.txt` and `requirements-build.txt`.

## [2.0.0] - 2026-05-31

Initial public release of GOLEM. Features:

- Folder watching with content-based duplicate detection
- Text extraction from `.txt`, `.pdf`, `.docx`, `.xlsx`
- Obsidian note generation in `<vault>/GOLEM/`
- File organisation into `<vault>/GOLEM Files/<category>/`
- SQLite + FTS5 full-text search
- Heuristic mode and 8 LLM providers (Groq, OpenAI, OpenRouter, xAI,
  NVIDIA NIM, Anthropic, Gemini, custom OpenAI-compatible)
- System tray, global hotkey, and floating search popup
- Undo for the latest organisation action
- Windows installer and macOS DMG with code signing
