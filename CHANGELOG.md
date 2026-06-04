# Changelog

All notable changes to GOLEM are documented in this file. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- **Build validation**: verified all build scripts parse correctly. Mypy is clean
  (0 errors). All 151 tests pass.

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
  macOS and tolerant of `\` vs `/` separators.
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
