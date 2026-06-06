# GOLEM Installation Guide

> **Version 2.1.0** — *WebView Launcher with AI-powered semantic search*

This guide covers installing GOLEM on a **fresh operating system** — whether you're setting up on a brand-new Windows PC, a new Mac, or a clean Linux install. Choose your platform below.

---

## Quick Start (3 minutes)

| Platform | Method | What you get |
|----------|--------|--------------|
| **Windows** | Download the installer (.exe) | Installed app with Start Menu & Desktop shortcuts |
| **macOS** | Download the DMG | Drag to Applications — done |
| **Linux** | AppImage or .deb | Run anywhere, or install system-wide |
| **Any OS** | Run from source (`pip install`) | For developers who want to hack on GOLEM |

---

## Table of Contents

- [Windows Installation](#windows-installation)
- [macOS Installation](#macos-installation)
- [Linux Installation](#linux-installation)
- [Run from Source (all platforms)](#run-from-source-all-platforms)
- [First-Time Setup](#first-time-setup)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)

---

## Windows Installation

### System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Windows 10 64-bit or Windows 11 |
| **CPU** | Intel Core i3 / AMD Ryzen 3 or better |
| **RAM** | 4 GB (8 GB recommended) |
| **Disk** | 200 MB for app + 50 MB for data |
| **Python** | Not required (installer bundles everything) |

### Option 1: Installer (Recommended)

1. **Download** `GOLEM-Setup-2.1.0.exe` from the [Releases page](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases)

2. **Double-click** the installer

3. **Windows SmartScreen** may show a warning — click **"More info"** then **"Run anyway"**

4. **Choose options:**
   - Install location (default: `%LOCALAPPDATA%\Programs\GOLEM`)
   - ✓ Create Start Menu shortcuts
   - ✓ Create Desktop shortcut
   - ✓ Launch GOLEM after install

5. Click **Install**

6. GOLEM launches automatically — proceed to [First-Time Setup](#first-time-setup)

### Option 2: Silent Install (IT Admins)

```powershell
# Default install
GOLEM-Setup-2.1.0.exe --silent

# Custom directory
GOLEM-Setup-2.1.0.exe --silent --install-dir "D:\GOLEM"

# No shortcuts
GOLEM-Setup-2.1.0.exe --silent --no-start-menu --no-desktop
```

### Option 3: Portable Binary

1. Download `GOLEM-2.1.0-windows-portable.zip`
2. Extract to any folder
3. Run `GOLEM.exe`

### Verify Download

```powershell
Get-FileHash -Path "GOLEM-Setup-2.1.0.exe" -Algorithm SHA256
```

Compare with the checksum in `SHA256SUMS.txt` on the Releases page.

---

## macOS Installation

### System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | macOS 11 (Big Sur) or later |
| **CPU** | Intel (x86_64) or Apple Silicon (arm64) |
| **RAM** | 4 GB (8 GB recommended) |
| **Disk** | 250 MB for app + 50 MB for data |
| **Python** | Not required (DMG bundles everything) |

### Step 1: Determine Your Architecture

Click the Apple menu  → **About This Mac**:
- If **Chip** says "Apple M1/M2/M3/M4" → download the **arm64** version
- If **Processor** says "Intel" → download the **x86_64** version

### Step 2: Download & Install

1. Download the correct DMG from the [Releases page](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases):
   - Apple Silicon: `GOLEM-2.1.0-macOS-arm64.dmg`
   - Intel: `GOLEM-2.1.0-macOS-x86_64.dmg`

2. **Double-click** the `.dmg` to mount it

3. **Drag** `GOLEM.app` into the `Applications` folder

4. **Eject** the disk image

5. **First launch:** Right-click `GOLEM.app` in Applications and select **Open** (required once to bypass Gatekeeper)

6. **Grant Accessibility permission** when prompted for the global hotkey:
   - Open **System Settings → Privacy & Security → Accessibility**
   - Toggle **GOLEM** on

### Alternative: Command-Line Install

```bash
# Mount DMG
hdiutil attach GOLEM-2.1.0-macOS-arm64.dmg

# Copy to Applications
cp -R /Volumes/GOLEM/GOLEM.app /Applications/

# Eject
hdiutil detach /Volumes/GOLEM
```

### Verify Download

```bash
shasum -a 256 GOLEM-2.1.0-macOS-arm64.dmg
codesign -dv --verbose=4 /Applications/GOLEM.app
```

---

## Linux Installation

### System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Ubuntu 22.04+, Debian 12+, Fedora 38+ |
| **Arch** | x86_64 or aarch64 (ARM64) |
| **RAM** | 4 GB (8 GB recommended) |
| **Disk** | 200 MB for app + 50 MB for data |
| **Dependencies** | `libc6 >= 2.31`, `libgtk-3-0` |

### Option 1: AppImage (Universal — Recommended)

Works on any Linux distro without installation:

```bash
# Download
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-x86_64.AppImage

# Make executable
chmod +x GOLEM-2.1.0-x86_64.AppImage

# Run
./GOLEM-2.1.0-x86_64.AppImage
```

> **Tip:** Move to `~/Applications/` and add to PATH for permanent access.

If you get a **FUSE error**:
```bash
# Install FUSE
sudo apt install fuse       # Debian/Ubuntu
sudo dnf install fuse       # Fedora

# Or extract and run directly
./GOLEM-2.1.0-x86_64.AppImage --appimage-extract
./squashfs-root/AppRun
```

### Option 2: .deb Package (Debian/Ubuntu)

```bash
# Download
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/golem_2.1.0_amd64.deb

# Install
sudo dpkg -i golem_2.1.0_amd64.deb

# Fix dependencies
sudo apt-get install -f

# Run
golem
```

### Option 3: tar.gz Archive

```bash
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v2.1.0/GOLEM-2.1.0-linux-x86_64.tar.gz
tar -xzf GOLEM-2.1.0-linux-x86_64.tar.gz
./GOLEM/GOLEM
```

### Option 4: Desktop Integration (Manual)

Create `~/.local/share/applications/golem.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=GOLEM
Comment=Local-first AI file manager with semantic search
Exec=/path/to/GOLEM
Terminal=false
Categories=Utility;Office;
```

### Verify Download

```bash
sha256sum GOLEM-2.1.0-x86_64.AppImage
```

---

## Run from Source (All Platforms)

For developers who want to run or modify the latest code:

### Step 1: Install Python 3.11+

<details>
<summary><b>Windows</b></summary>

1. Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
2. **Check** "Add Python to PATH" during installation
3. Open **Command Prompt** and verify:
   ```cmd
   python --version
   ```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
# Using Homebrew (recommended)
brew install python@3.11

# Verify
python3.11 --version
```
</details>

<details>
<summary><b>Linux (Ubuntu/Debian)</b></summary>

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```
</details>

### Step 2: Clone & Setup

```bash
# Clone the repository
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER.git
cd GOLEM-AI-FILE-MANAGER

# Create virtual environment
python3.11 -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Launch

```bash
# Launch the WebView launcher (v2.1 — new modern UI)
python golem_webview.py

# OR launch legacy Tkinter UI
python main.py
```

### Step 4 (Optional): Build Installer

```powershell
# Windows — requires PowerShell
.\build_windows_installer.ps1
```

```bash
# macOS
./build_macos_installer.sh

# Linux
./build_linux_installer.sh
```

---

## First-Time Setup

When GOLEM launches for the first time, follow the on-screen setup:

### Step 1: Configure Folders

- **Watched Folder** — Where GOLEM watches for files to index. Drop files here and GOLEM will automatically organize them.
- **Obsidian Vault** — Your Obsidian vault folder. GOLEM creates beautifully formatted notes here.

> If you don't use Obsidian, GOLEM will create a default vault folder in your AppData directory.

### Step 2: Choose an AI Provider

| Provider | Free Tier? | API Key Needed? | Best For |
|----------|-----------|-----------------|----------|
| **Heuristic** (no API) | ✅ Always free | ❌ No | Quick local use |
| **Groq** | ✅ Free tier | ✅ Yes | Fast + free |
| **OpenAI** | ❌ Paid | ✅ Yes | Best quality |
| **Anthropic/Claude** | ❌ Paid | ✅ Yes | Long documents |
| **Google Gemini** | ✅ Free tier | ✅ Yes | Good free option |
| **OpenRouter** | ✅ Free models | ✅ Yes | Many model choices |

**Heuristic mode** works completely offline and uses keyword analysis — no API key, no internet, no cost.

### Step 3: Accept Terms

Review and accept the Terms of Service.

### Step 4: Click "Awaken GOLEM"

GOLEM starts scanning your watched folder and building its index.

### Step 5: Use the Launcher

Press **`Ctrl+Space`** (Windows/Linux) or **`Cmd+Shift+Space`** (macOS) anywhere to open the GOLEM launcher.

What you can do:
- **Type naturally** — "pricing strategy pdf" or "meeting notes from last week"
- **Navigate** with ↑↓ arrows
- **Open files** with Enter
- **Reveal in Explorer/Finder** with Cmd/Ctrl+Enter
- **Filter results** with Tab or click filter pills
- **See related files** — purple `#tag` chips show graph-discovered connections

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Installer blocked** | Click "More info" → "Run anyway" (Windows) or right-click → Open (macOS) |
| **"Python not found"** | Not needed — the installer bundles everything |
| **Hotkey doesn't work** | On macOS: grant Accessibility permission. On Windows: check for conflicting apps (IME, Spotlight) |
| **No results when searching** | GOLEM needs indexed files. Drop a few documents into the watched folder and wait for the scan. |
| **Antivirus flags the app** | Add an exclusion for the install directory |
| **AppImage FUSE error** | `sudo apt install fuse` or use `--appimage-extract` |
| **WebView window is blank** | Make sure `pywebview` is installed: `pip install pywebview` |
| **"No file index found"** | First run creates the index automatically. If it doesn't, trigger a scan from the tray menu. |
| **macOS Gatekeeper** | Right-click → Open the first time. After that, normal double-click works. |

---

## Uninstalling

### Windows

**Via Settings:**
1. Open **Settings → Apps → Installed apps**
2. Search for **GOLEM**
3. Click **Uninstall**

**Via installer:**
```powershell
GOLEM-Setup-2.1.0.exe --uninstall --silent
```

### macOS

```bash
rm -rf /Applications/GOLEM.app
rm -rf ~/.golem     # removes data too
```

### Linux

```bash
# If installed via .deb
sudo apt remove golem

# If using AppImage — just delete the file
rm ~/Applications/GOLEM-2.1.0-x86_64.AppImage
```

---

## Data Directory

GOLEM stores its database and settings at:

| Platform | Path |
|----------|------|
| **Windows** | `%LOCALAPPDATA%\GOLEM\` |
| **macOS / Linux** | `~/.golem/` |

Override with the `GOLEM_DATA_DIR` environment variable.

---

## Getting Help

- **Documentation**: [codebuff.com/docs](https://codebuff.com/docs)
- **GitHub Issues**: [github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/issues](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/issues)
- **FAQ**: See [docs/FAQ.md](FAQ.md)
