# Download & Install GOLEM on Linux

> **Status:** Linux builds are produced by CI but are **community-supported**. The primary target platforms are Windows and macOS. Linux users may need to install additional system dependencies.

## System Requirements

- **Distribution:** Ubuntu 22.04+, Debian 12+, Fedora 38+, or any glibc-based distro
- **Architecture:** x86_64 (Intel/AMD) or aarch64 (ARM64)
- **Disk space:** ~120 MB for installation + 50 MB for the data directory
- **Dependencies:** `libc6 >= 2.31`, Python 3.11+ (for source installs)
- **Optional:** An API key from Groq, OpenAI, Anthropic, or another supported provider

## Download Options

### Option 1: AppImage (universal, recommended)

Download from the [Releases page](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases):

| Architecture | File |
|-------------|------|
| **x86_64** | `GOLEM-<version>-x86_64.AppImage` |
| **aarch64** | `GOLEM-<version>-aarch64.AppImage` |

### Option 2: .deb Package (Debian/Ubuntu)

| Architecture | File |
|-------------|------|
| **amd64** | `golem_<version>_amd64.deb` |
| **arm64** | `golem_<version>_arm64.deb` |

### Option 3: tar.gz Archive

| Architecture | File |
|-------------|------|
| **x86_64** | `GOLEM-<version>-linux-x86_64.tar.gz` |
| **aarch64** | `GOLEM-<version>-linux-aarch64.tar.gz` |

### Option 4: Run from Source (developers)

```bash
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER
cd GOLEM-AI-FILE-MANAGER
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Installation Guide

### AppImage (any distro)

```bash
# Download the AppImage
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v<version>/GOLEM-<version>-x86_64.AppImage

# Make executable
chmod +x GOLEM-<version>-x86_64.AppImage

# Run
./GOLEM-<version>-x86_64.AppImage
```

> **Tip:** Move the AppImage to a permanent location like `~/Applications/` and add it to your PATH or desktop launcher.

### Debian/Ubuntu (.deb)

```bash
# Download the .deb
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v<version>/golem_<version>_amd64.deb

# Install
sudo dpkg -i golem_<version>_amd64.deb

# Fix any missing dependencies
sudo apt-get install -f

# Run
golem
```

### tar.gz Archive

```bash
# Download and extract
wget https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases/download/v<version>/GOLEM-<version>-linux-x86_64.tar.gz
tar -xzf GOLEM-<version>-linux-x86_64.tar.gz

# Run
./GOLEM/GOLEM
```

### Desktop Integration (manual)

Create a `.desktop` file at `~/.local/share/applications/golem.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=GOLEM
Comment=Local-first AI file manager for Obsidian
Exec=/path/to/GOLEM
Terminal=false
Categories=Utility;Office;
```

## First Run

1. **Launch GOLEM** from your application launcher or terminal
2. The **onboarding wizard** appears:
   - **Step 1:** Pick a **Watched folder** and your **Obsidian vault**
   - **Step 2:** Choose an AI provider or select **Heuristic mode**
   - **Step 3:** Accept the Terms of Service
   - **Step 4:** Review and click **Awaken GOLEM**
3. GOLEM starts scanning
4. Press **`Ctrl+Shift+Space`** to open the search popup

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **AppImage: "FUSE error"** | Install fuse: `sudo apt install fuse` or extract: `./AppImage --appimage-extract && ./squashfs-root/AppRun` |
| **.deb: dependency errors** | Run `sudo apt-get install -f` to resolve |
| **No tray icon** | Install a system tray: `sudo apt install libappindicator3-1` |
| **Hotkey not working** | Try `python main.py --no-hotkey` and use the tray menu instead |
| **Data directory location** | `~/.golem/` |

## Verify the Download

```bash
# SHA-256 checksum
sha256sum GOLEM-<version>-x86_64.AppImage

# Compare with the value in SHA256SUMS.txt on the Releases page
```
