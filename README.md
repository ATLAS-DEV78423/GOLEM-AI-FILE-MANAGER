# GOLEM AI File Manager

GOLEM is a local-first desktop file manager for Windows and macOS. It watches a folder, extracts text from supported files, writes Obsidian notes, organizes files into category folders, and gives you a fuzzy search popup for finding files by description.

## What it does

- Watches a chosen folder for new files
- Extracts text from `.txt`, `.pdf`, `.docx`, and `.xlsx`
- Creates an Obsidian note for each indexed file
- Moves files into `GOLEM Files/<category>/`
- Stores a searchable local SQLite index
- Supports local heuristic mode or remote AI providers
- Lets you search with a global `Ctrl+Space` hotkey
- Supports undo for the latest organization action
- Ships Windows and macOS installer flows

## Quick Start

1. Install the dependencies from [requirements.txt](requirements.txt).
2. Run `python main.py`.
3. Complete onboarding:
   - choose a watched folder
   - choose an Obsidian vault
   - choose a provider or heuristic mode
   - accept the Terms of Service
4. Use `Ctrl+Space` to search.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Usage](docs/USAGE.md)
- [Configuration](docs/CONFIGURATION.md)
- [AI Providers](docs/PROVIDERS.md)
- [Security](docs/SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Releases](docs/RELEASE.md)
- [FAQ](docs/FAQ.md)

## Release artifacts

- Windows release scripts: [release_windows.ps1](release_windows.ps1), [build_windows_installer.ps1](build_windows_installer.ps1)
- macOS release scripts: [release_macos.sh](release_macos.sh), [build_macos_installer.sh](build_macos_installer.sh)
- Release checklist: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

## Legal

The bundled terms document is shipped in [assets/legal/terms_of_service.md](assets/legal/terms_of_service.md).

## Project reference

For the original product vision and roadmap, see [GOLEM_Master_Reference.md](GOLEM_Master_Reference.md).
