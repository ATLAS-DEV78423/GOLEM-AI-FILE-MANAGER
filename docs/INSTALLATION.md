# Installation

## Requirements

- Windows 10/11 or macOS
- Python 3.11+ for local development
- Obsidian if you want generated notes to land in a vault
- Optional AI provider API key if you want AI summaries and reranking

## Development install

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the app:

```bash
python main.py
```

## Windows packaging

- Build the app bundle and installer with [build_windows_installer.ps1](../build_windows_installer.ps1).
- Build the signed release with [release_windows.ps1](../release_windows.ps1).

## macOS packaging

- Build the app bundle and DMG with [build_macos_installer.sh](../build_macos_installer.sh).
- Build the signed release with [release_macos.sh](../release_macos.sh).

## First launch

On first launch, GOLEM opens onboarding and asks for:

- watched folder
- Obsidian vault
- provider choice
- API key if needed
- Terms of Service acceptance

