# Download & Install GOLEM on macOS

## System Requirements

- **OS:** macOS 11 (Big Sur) or later (Intel & Apple Silicon supported)
- **Disk space:** ~150 MB for installation + 50 MB for the data directory
- **Python:** Not required (the DMG bundles everything)
- **Permissions:** Accessibility access (for the global hotkey)
- **Optional:** An API key from Groq, OpenAI, Anthropic, or another supported provider

## Download

Download the latest macOS release from the [Releases page](https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER/releases):

**Choose your architecture:**

| Architecture | File |
|-------------|------|
| **Intel Mac** (2020 and earlier) | `GOLEM-macOS-x86_64.dmg` |
| **Apple Silicon Mac** (M1/M2/M3/M4) | `GOLEM-macOS-arm64.dmg` |

> **Note:** If you're unsure which Mac you have, click the Apple menu  > **About This Mac**. If the chip is listed as "Apple M..." you need the `arm64` version.

## Installation Guide

### Standard Install

1. **Download** the `.dmg` file for your Mac
2. **Double-click** the `.dmg` to mount it
3. **Drag** the `GOLEM.app` icon into the `Applications` folder
4. **Eject** the disk image
5. **First launch:** Right-click `GOLEM.app` in Applications and select **Open** (this is needed only once to bypass Gatekeeper)
6. If prompted, grant **Accessibility** permission for the global hotkey (`Ctrl+Shift+Space`):
   - Open **System Settings > Privacy & Security > Accessibility**
   - Toggle **GOLEM** on

### Command-line Install

```bash
# Mount the DMG
hdiutil attach GOLEM-macOS-arm64.dmg

# Copy to Applications
cp -R /Volumes/GOLEM/GOLEM.app /Applications/

# Eject
hdiutil detach /Volumes/GOLEM
```

### Uninstalling

```bash
# Delete the app
rm -rf /Applications/GOLEM.app

# Remove data (optional — keeps your index)
rm -rf ~/.golem
```

## First Run

1. **Launch GOLEM** from Applications
2. The **onboarding wizard** appears:
   - **Step 1:** Pick a **Watched folder** and your **Obsidian vault**
   - **Step 2:** Choose an AI provider or select **Heuristic mode** (no API key needed)
   - **Step 3:** Accept the Terms of Service
   - **Step 4:** Review and click **Awaken GOLEM**
3. GOLEM starts scanning your watched folder
4. Press **`Ctrl+Shift+Space`** anywhere to open the search popup

## Code Signing & Notarization

Production releases are code-signed and notarized by Apple. If you see "GOLEM is from an unidentified developer":

1. **Right-click** the app and select **Open**
2. Click **Open** in the dialog
3. After the first launch, the app will open normally

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **"GOLEM is damaged" warning** | Run `xattr -cr /Applications/GOLEM.app` in Terminal |
| **Hotkey not working** | Grant Accessibility permission in System Settings |
| **App won't open** | Run `spctl --assess --verbose /Applications/GOLEM.app` to check |
| **Data directory location** | `~/.golem/` (hidden — press `Cmd+Shift+.` in Finder to show it) |

## Verify the Download

```bash
# Check SHA-256 checksum
shasum -a 256 GOLEM-macOS-<arch>.dmg

# Verify code signature
codesign -dv --verbose=4 /Applications/GOLEM.app
```

Compare the checksum with the value in `SHA256SUMS.txt` on the Releases page.
