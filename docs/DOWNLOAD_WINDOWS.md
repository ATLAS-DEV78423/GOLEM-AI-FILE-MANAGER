# Download & Install GOLEM on Windows

## System Requirements

- **OS:** Windows 10 or Windows 11 (64-bit)
- **Disk space:** ~100 MB for installation + 50 MB for the data directory
- **Python:** Not required (the installer bundles everything)
- **Optional:** An API key from Groq, OpenAI, Anthropic, or another supported provider

## Download Options

### Option 1: Installer (recommended)

Download the latest Windows installer from the [Releases page](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases):

- **File:** `GOLEM-Setup-<version>.exe`

### Option 2: Standalone portable binary

- **File:** `GOLEM.exe` (inside `GOLEM-<version>-windows-portable.zip`)

## Installation Guide

### Using the Installer

1. **Download** `GOLEM-Setup-<version>.exe`
2. **Double-click** the installer
3. **Choose install location** (default: `%LOCALAPPDATA%\Programs\GOLEM`)
4. **Select options:**
   - ✓ Create Start Menu shortcuts
   - ✓ Create Desktop shortcut
   - ✓ Launch GOLEM after install
5. Click **Install**
6. GOLEM launches automatically — complete the onboarding wizard

### Silent Installation (for IT administrators)

```powershell
# Install with defaults
GOLEM-Setup-<version>.exe --silent

# Custom install directory
GOLEM-Setup-<version>.exe --silent --install-dir "D:\Programs\GOLEM"

# No shortcuts
GOLEM-Setup-<version>.exe --silent --no-start-menu --no-desktop
```

### Uninstalling

**Via Settings:**
1. Open **Settings > Apps > Installed apps**
2. Search for **GOLEM**
3. Click **Uninstall**

**Via command line:**
```powershell
GOLEM-Setup-<version>.exe --uninstall --silent
```

## First Run

1. **Launch GOLEM** from the Start Menu or Desktop shortcut
2. The **onboarding wizard** appears:
   - **Step 1:** Pick a **Watched folder** (where you'll drop files) and your **Obsidian vault** folder
   - **Step 2:** Choose an AI provider (or "Heuristic" mode for no API key)
   - **Step 3:** Accept the Terms of Service
   - **Step 4:** Review and click **Awaken GOLEM**
3. GOLEM starts scanning your watched folder
4. Press **`Ctrl+Shift+Space`** anywhere to open the search popup

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Installer blocked by Windows Defender** | Click "More info" then "Run anyway" |
| **"Python not found"** | This is normal — the installer includes everything |
| **Antivirus flags the installer** | Add an exclusion for the install directory |
| **Tray icon not appearing** | Run `GOLEM.exe --no-tray` to check for errors |

## Verify the Download

After downloading, verify the SHA-256 checksum:

```powershell
Get-FileHash -Path "GOLEM-Setup-<version>.exe" -Algorithm SHA256
```

Compare the output with the checksum listed in `SHA256SUMS.txt` on the Releases page.
