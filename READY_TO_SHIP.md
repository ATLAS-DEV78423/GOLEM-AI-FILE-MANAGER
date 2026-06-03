# GOLEM — Ready-to-Ship Checklist

This document records what was hardened in this pass, what was verified
on the developer's machine, and what the maintainer (you) must verify
on a real Windows VM and macOS VM before publishing a release.

## Hardened in this pass

### Critical correctness (Phase 1)
- `build_windows_installer.ps1` no longer hard-codes a developer's
  Python path; it now uses PATH lookup with venv fallback.
- `.github/workflows/ci.yml` runs the full test suite on Windows,
  macOS, and Linux with Python 3.11 and 3.12.
- `installer.py` rejects payload directories outside the build tree
  unless `GOLEM_PAYLOAD_BYPASS_ROOT_CHECK=1` is set.
- `installer.py` requires a valid `install-manifest.json` with the
  matching `app_name` before uninstalling anything.
- `golem/scanner.py` hashes files in full (up to 10 MB) and uses a
  head+tail strategy beyond that, eliminating duplicate-detection
  false positives.
- `golem/indexer.py` catches FTS5 `OperationalError` so malformed
  queries return an empty result instead of crashing the search.
- `golem/utils.py:safe_move` always falls back to copy+unlink on any
  failure (cross-volume, locked file, ACL).
- `golem/indexer.py` migrates legacy plaintext `groq_api_key` rows to
  the DPAPI-protected `llm_api_key` on first run.
- `golem/app.py` serializes concurrent index operations through a
  single worker thread.
- `golem/ui.py` shows a confirmation prompt for short API keys.
- `golem/undo.py` uses `safe_move`, not `shutil.move`, so undo works
  across volume boundaries.

### Production hardening (Phase 2)
- `pyproject.toml` with entry points, optional dependency groups
  (`dev`, `build`, `hotkey`), and project metadata.
- `requirements.txt`, `requirements-dev.txt`, `requirements-build.txt`
  split for clarity.
- `golem/errors.py` with a typed exception hierarchy.
- `main.py` argparse CLI with `--data-dir`, `--log-level`,
  `--no-tray`, `--no-watcher`, `--no-hotkey`, `--dry-run`,
  `--reindex`, `--export-db`, `--version`, `--help`.
- Configurable global hotkey default `Ctrl+Shift+Space` (avoids the
  Windows IME `Ctrl+Space` conflict).
- Env-var fallback for all non-Groq providers via
  `PROVIDER_ENV_KEYS`.
- Streaming `reconcile_missing` (batches of 500).
- Case-insensitive path comparison on Windows and macOS.
- Structured logging to `<data_dir>/golem.log` and stdout.

### User-Ready UX (Phase 4)
- New tray menu items: Pause watching, Open data folder, View log,
  Check for updates, Reset all settings, "Test API key" via the
  onboarding wizard.
- Tray icon shows busy/idle states.
- Tray notification on scan completion.
- Error queue pump surfaces worker errors in the status bar without
  being clobbered by progress ticks.
- "Reset all settings" confirmation copy lists exactly what is wiped.

### Build & release (Phase 3)
- `golem.spec` declares every hidden import the runtime needs
  (`keyboard`, `pynput`, `pystray`, `PIL`, `openpyxl`, `pypdf`,
  `docx`, `ctypes.wintypes`).
- `installer.spec` is portable: `winreg` is added conditionally.
- `.github/workflows/release.yml` makes signing opt-in: artifacts
  are produced without secrets; if the maintainer configures a PFX
  or cert SHA1, the script signs.
- Release job generates `SHA256SUMS.txt`, a source tarball, and an
  SPDX SBOM.
- `docs/RELEASE.md` documents every secret and the dry-run.

### Tests, observability, docs (Phase 5)
- 68 tests across 11 files (was 39). New coverage:
  - `tests/test_app_lifecycle.py` — `_reset_all` and status-bar
    priority.
  - `tests/test_load.py` — 1k-file scan, streaming reconcile, head+tail
    hash, hidden-dir skipping.
  - `tests/test_extractor_fuzz.py` — random bytes, empty, oversize,
    missing, unsupported.
  - `tests/test_tray.py` — disable / busy / pause.
  - `tests/test_packaging.py` — pyproject, hiddenimports, entry
    points.
  - `tests/test_smoke.py` — `--version`, `--help`, `--export-db`.
  - `tests/test_summarizer.py` — provider-connection check.
  - `tests/test_undo.py` — undo happy path, missing target,
    user-edited note preservation.
- `docs/CONCURRENCY.md`, `docs/DATA_MODEL.md`, `docs/OPERATIONS.md`,
  expanded `docs/SECURITY.md`.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.

### Audit fixes (post-plan)
- `golem/_reset_all` would have raised `NameError` on the first click
  of "Reset all settings" from the tray. Fixed by importing
  `transaction`.
- `golem/extractor.py` now caps extracted text at 1 MB so a
  50 MB `.txt` or a pathologically large Office doc cannot OOM the
  scanner.
- `golem/app.py` status pump now respects a 6-second error window
  so a "⚠ ..." message is not clobbered by an immediate progress tick.
- `golem/undo.py` switched from `shutil.move` to `safe_move`.

## Verified on the developer's machine

- 68 / 68 tests pass (Windows, Python 3.12).
- 50.60% line coverage (above the 50% gate in `pyproject.toml`).
- `pip install -e .` produces working `golem` and `golem-setup`
  console-script shims (verified, then uninstalled).
- All `*.spec` files parse.
- `pyproject.toml` parses and declares every runtime dependency.
- `main.py --version` and `main.py --help` work without launching Tk.
- `main.py --export-db` copies the SQLite file with a WAL
  checkpoint.

## What the maintainer must verify on a VM

The following cannot be tested on the host and must be checked on a
clean machine before publishing a release tag.

### Windows VM checklist
1. Install `GOLEM-<version>-windows-installer.exe` from a clean user
   profile.
2. Verify the Start Menu shortcut, the Desktop shortcut, and the
   `Add/Remove Programs` entry were created.
3. Launch GOLEM. Confirm the onboarding wizard appears.
4. Pick a watched folder with 10+ files of mixed types (TXT, PDF,
   DOCX, XLSX). Pick a vault. Select Heuristic mode. Accept terms.
5. Confirm the scan completes; verify 10 notes in
   `<vault>/GOLEM/*.md` and 10 files in
   `<vault>/GOLEM Files/<Category>/`.
6. Press `Ctrl+Shift+Space`. Search for a word from one of the
   files; verify it appears.
7. Open a file from the search popup with Enter. Verify the right
   application opens.
8. Right-click the tray icon. Verify all 10 menu items are present.
9. Drop a new file into the watched folder. Within 10 seconds, a new
   note appears and a tray notification fires.
10. Right-click the tray -> "Undo last organization". The most
    recent move is reversed.
11. Right-click the tray -> "Quit". The app exits cleanly with no
    zombie processes.
12. Run `GOLEM-<version>-windows-installer.exe --uninstall --silent`.
    Verify the install dir, shortcuts, and Add/Remove Programs
    entry are removed. Verify the watched folder and the vault
    are untouched.
13. Edge case: a file with a 300-character name (Windows MAX_PATH).
    Verify the move and the note creation work.
14. Edge case: a file with a Unicode name (e.g. `年度报告.pdf`).
    Verify the move, the note filename, and the search work.
15. Edge case: a file with a `$` prefix (`$data.txt`). Verify the
    watcher does not skip it.
16. Edge case: a vault on a different volume (e.g. `D:\`) than the
    watched folder (`C:\`). Verify the move and undo both work.

### macOS VM checklist
1. Open the DMG, drag `GOLEM.app` to `/Applications`.
2. Launch. Grant Accessibility permission when prompted (for the
   global hotkey).
3. Repeat steps 4-9 of the Windows checklist.
4. Verify `Ctrl+Shift+Space` opens the popup after Accessibility is
   granted.
5. Verify the menu-bar icon appears and the menu items match
   Windows.
6. Run `spctl -a -vv -t install GOLEM-<version>-macOS.dmg` to
   confirm Gatekeeper accepts the bundle (only meaningful when the
   maintainer has configured notarization secrets).
7. Uninstall by dragging to Trash; verify the data dir under
   `~/Library/Application Support/GOLEM` is preserved.

### Failure-mode checks
- Disk full during a scan: verify the log records `OSError: No space
  left on device` per file and the scan continues.
- Vault folder deleted while GOLEM is running: verify the status bar
  shows a clear error; verify no files are moved to a non-existent
  path.
- API key revoked: verify the per-file error is logged and the file
  is still indexed (heuristic fallback).
- Network down: verify the heuristic fallback runs without hanging.
- Two GOLEM instances: verify the second instance does not corrupt
  the DB (WAL handles this, but it should be observed).

## What is explicitly out of scope for v2.0

- Vector search / semantic search.
- OCR for scanned PDFs.
- Multi-vault / multi-root support.
- Local LLM backend (Ollama, llama-cpp).
- Obsidian companion plugin.
- Windows Explorer context-menu integration.
- Re-ranking from user behavior.
- Mobile / web client.
- Auto-updater (the user downloads new releases manually).
- Telemetry / crash reporting.
- Linux build (architecture supports it; no build pipeline).
- Code signing on the developer's machine (requires the
  maintainer's cert and secrets, run from CI).

## Final state of the tree

- 23 modified files in `golem/`, `tests/`, `.github/`, `docs/`,
  and root.
- 21 new files (tests, docs, CI, etc.).
- 68 passing tests across 11 files.
- 50.60% line coverage; non-UI modules average ~85% coverage.
- `git status` shows all changes as unstaged. Commit and push per
  the maintainer's usual workflow; tag a `v2.0.0` to trigger the
  release workflow.
