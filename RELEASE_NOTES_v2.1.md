# 🚀 GOLEM v2.1.0 — WebView Launcher

**A brand-new floating search launcher with animations, graph-powered search, and cross-platform PyWebView UI.**

---

## ✨ What's New

### 🖥️ Beautiful New Launcher UI

The old Tkinter popup is gone. GOLEM now opens a frameless, dark-themed search window powered by HTML/CSS/JS + PyWebView:

- **Outfit + JetBrains Mono fonts** — premium typography, no system fonts
- **Animations everywhere** — 130ms scale+fade window open, 180ms staggered item entrance, spring bounces on icons and pills, pulsing status dot
- **Skeleton shimmer loader** — elegant animated placeholders while searching
- **Match-type pills** — color-coded badges show *why* each result matched (keyword, semantic, both, via entity)
- **Graph chips** — purple `#tag` and teal `📎 related file` chips from graph-discovered connections
- **Type filter pills** — filter results by type (All, Files, Videos, Notes, Audio, Web)

### 🔍 Smarter Search with Graph Traversal

- **Deeper graph walking** — depth-2 traversal surfaces tags → related files and categories → member files
- **Folder-proximity boost** — files sharing a directory with the top result get ranked higher
- **Graph data in every result** — related tags, files, and categories shown directly in the UI

### ⌨️ Full Keyboard Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate results |
| `Enter` | Open file |
| `Cmd/Ctrl+Enter` | Reveal in Finder/Explorer |
| `Tab` | Cycle type filters |
| `Escape` | Close launcher |
| `Ctrl+Space` / `Cmd+Shift+Space` | Global toggle hotkey |

---

## 📦 Download

### Windows

| File | Description |
|------|-------------|
| [GOLEM-Setup-2.1.0.exe](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-Setup-2.1.0.exe) | Installer (recommended) |
| [GOLEM-2.1.0-windows-portable.zip](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-windows-portable.zip) | Portable binary |

### macOS

| File | Description |
|------|-------------|
| [GOLEM-2.1.0-macOS-arm64.dmg](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-macOS-arm64.dmg) | Apple Silicon (M1/M2/M3/M4) |
| [GOLEM-2.1.0-macOS-x86_64.dmg](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-macOS-x86_64.dmg) | Intel Mac |

### Linux

| File | Description |
|------|-------------|
| [GOLEM-2.1.0-x86_64.AppImage](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-x86_64.AppImage) | Universal AppImage |
| [GOLEM-2.1.0-aarch64.AppImage](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-aarch64.AppImage) | ARM64 AppImage |
| [golem_2.1.0_amd64.deb](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/golem_2.1.0_amd64.deb) | Debian/Ubuntu package |
| [GOLEM-2.1.0-linux-x86_64.tar.gz](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-linux-x86_64.tar.gz) | Portable archive |

### Source

- [Source code (tar.gz)](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/archive/refs/tags/v2.1.0.tar.gz)
- [SHA256SUMS.txt](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/SHA256SUMS.txt)

---

## 🚀 Quick Start

### Windows
1. Download `GOLEM-Setup-2.1.0.exe`
2. Double-click → Install → Launch
3. Press `Ctrl+Space` to open the launcher

### macOS
1. Download the correct DMG for your Mac
2. Drag `GOLEM.app` to Applications
3. Right-click → Open (first time only)
4. Press `Cmd+Shift+Space` to open the launcher

### Linux
```bash
chmod +x GOLEM-2.1.0-x86_64.AppImage
./GOLEM-2.1.0-x86_64.AppImage
```

### From Source
```bash
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER.git
cd GOLEM-AI-FILE-MANAGER
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python golem_webview.py
```

---

## 🧩 Full Changelog

### Major — New PyWebView Launcher UI
- Frameless HTML/CSS/JS search window replacing legacy Tkinter
- Outfit + JetBrains Mono fonts for premium typography
- Animations: launchIn (130ms), itemIn stagger (180ms), spring icons/pills
- Skeleton shimmer loader during search
- Status dot with pulsing glow animation
- ESC badge and keyboard hint hover effects
- Full keyboard navigation (↑↓ Enter Tab Escape)
- Type filter pills and match-type color-coded pills
- Term highlighting in file names and snippets
- Graceful empty state and idle welcome screen

### Enhanced — Graph-Powered Search
- Graph traversal depth increased to 2 hops
- Folder-proximity confidence boost for nearby files
- Graph chips (tags, related files) shown in search results
- Deduplicated and sorted related items

### New — golem_webview.py Entry Point
- PyWebView integration with full JS↔Python bridge
- PollingWatcher for automatic file indexing
- Periodic status updates (file count every 30s)
- Auto-scan on first run
- Global hotkey registration (Ctrl+Space / Cmd+Shift+Space)

### Improved — Installer & Build
- golem.spec targets webview entry point with pywebview deps
- pywebview>=6.2 added to requirements
- Comprehensive INSTALLATION.md for Windows/macOS/Linux
- Version bumped to 2.1.0

---

## ⚠️ Notes

- **Windows**: If SmartScreen blocks the installer, click "More info" → "Run anyway"
- **macOS**: Right-click → Open the first time to bypass Gatekeeper
- **No API key?** Use "Heuristic" mode — works fully offline with no key needed
- **First launch**: GOLEM auto-creates default folders and triggers an initial scan
- **Hotkey conflict on macOS**: Uses `Cmd+Shift+Space` to avoid Spotlight conflict

---

*Full documentation: [docs/INSTALLATION.md](docs/INSTALLATION.md) | [FAQ](docs/FAQ.md)*
