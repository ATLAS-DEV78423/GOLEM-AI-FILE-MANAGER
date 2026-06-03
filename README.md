# GOLEM AI File Manager

[![ci](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/actions/workflows/ci.yml/badge.svg)](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/actions/workflows/ci.yml)
[![release](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/actions/workflows/release.yml/badge.svg)](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

GOLEM is a local-first desktop file manager for Windows and macOS. It watches a folder you choose, extracts text from supported files, writes Obsidian notes, organizes files into category folders, and gives you a global hotkey for finding files by description.

Everything runs on your machine. The only outbound network calls are to the AI provider you have configured (or none, if you use Heuristic mode).

## What it does

- Watches a chosen folder for new and changed files
- Extracts text from `.txt`, `.pdf`, `.docx`, and `.xlsx`
- Creates an Obsidian note (`.md`) for each indexed file
- Moves files into `<vault>/GOLEM Files/<category>/`
- Stores a searchable local SQLite + FTS5 index
- Supports **Heuristic mode** (no API key) and remote AI providers
  (Groq, OpenAI, OpenRouter, xAI, NVIDIA NIM, Anthropic, Gemini, custom)
- Global hotkey `Ctrl+Shift+Space` opens the search popup
- Undo for the latest organization action
- Tray menu for re-scan, undo, dry-run, view log, open data folder,
  reset all settings, check for updates

## System requirements

- **Windows 10 or 11** (installer is built with PyInstaller 6.x)
- **macOS 11+** (DMG is built with `hdiutil`)
- ~100 MB free disk for the install + 50 MB for the data dir
- An AI provider key OR willingness to use Heuristic mode

## Quick start (users)

1. Download the latest release for your platform from the
   [Releases](../../releases) page.
2. Run the installer (Windows) or open the DMG and drag to Applications
   (macOS).
3. Launch GOLEM. Complete the onboarding wizard (watched folder,
   vault, provider or Heuristic, accept the terms).
4. Drop a file into the watched folder.
5. Press `Ctrl+Shift+Space` to open the search popup.

## Quick start (developers)

```sh
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER
cd GOLEM-AI-FILE-MANAGER
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-build.txt
python main.py
```

The CLI flags below are also available:

```sh
python main.py --help            # List all flags
python main.py --no-tray         # Run without a system tray
python main.py --no-watcher      # Run without a polling watcher
python main.py --no-hotkey       # Run without a global hotkey
python main.py --dry-run         # Index but do not move files
python main.py --reindex         # Wipe the index and rebuild from disk
python main.py --export-db PATH  # Copy golem.db to PATH and exit
python main.py --data-dir PATH   # Override the data directory
python main.py --log-level DEBUG # DEBUG / INFO / WARNING / ERROR
python main.py --version         # Print the version and exit
```

`--export-db` is the safe way to send your index to support — it
copies the SQLite file with the WAL checkpointed, leaving the
running app untouched.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Usage](docs/USAGE.md)
- [Configuration](docs/CONFIGURATION.md)
- [AI Providers](docs/PROVIDERS.md)
- [Security](docs/SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Concurrency model](docs/CONCURRENCY.md)
- [Data model](docs/DATA_MODEL.md)
- [Operations](docs/OPERATIONS.md)
- [Release process](docs/RELEASE.md)
- [FAQ](docs/FAQ.md)

## Release artifacts

GitHub Releases publishes:

- `GOLEM-<version>-windows-installer.exe` — Windows self-extracting
  installer
- `GOLEM-<version>-windows.exe` — Standalone Windows binary (no
  installer)
- `GOLEM-<version>-macOS.dmg` — macOS disk image
- `GOLEM-<version>-source.tar.gz` — Source tarball
- `SHA256SUMS.txt` — Checksums for every artifact
- `golem.spdx.json` — SPDX SBOM

Additional artifacts produced by CI on `main`:

- `GOLEM-<version>-linux.tar.gz` — One-folder tarball (one-click run of the bundled binary)
- `GOLEM-<version>.AppImage` — Optional AppImage when `appimagetool` is available on the runner

CI behavior and releases:

- A draft GitHub Release is automatically created on successful CI runs on `main` (the draft is not published automatically).
- A visual smoke test runs on the `ubuntu-latest` runner to exercise the Linux build briefly under `xvfb`.
- This repository uses `main` as the single source-of-truth branch. Artifacts are built from `main` and attached to draft releases for manual publishing.

See [docs/RELEASE.md](docs/RELEASE.md) for the build and signing
process.

## Project status

GOLEM is a shipping product, not a prototype. The CI runs the full
test suite on every push to `main` across Windows, macOS, and Linux
with Python 3.11 and 3.12. See
[.github/workflows/ci.yml](.github/workflows/ci.yml).

## Legal

GOLEM is MIT-licensed. The bundled terms document is shipped in
[assets/legal/terms_of_service.md](assets/legal/terms_of_service.md).
By completing onboarding you agree to the terms at the bundled
version; bumps to the terms require a fresh acceptance.

## Project reference

For the original product vision and roadmap, see
[GOLEM_Master_Reference.md](GOLEM_Master_Reference.md).
