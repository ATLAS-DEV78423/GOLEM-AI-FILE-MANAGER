# Windows VM Release Guide

This guide is the shortest path from a clean Windows 11 VM to a published GOLEM release on GitHub, plus the steps a tester should follow after downloading it.

## 1. Prepare the Windows 11 VM

- Create a fresh VirtualBox snapshot before changing anything.
- Install **Python 3.11+**.
- Install **Git**.
- Install the **Windows 10/11 SDK** if you want to code-sign locally.
- Give the VM at least 4 GB RAM and 10 GB free disk space.

## 2. Clone the repo

```powershell
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER.git
cd GOLEM-AI-FILE-MANAGER
```

## 3. Set up the build environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

## 4. Run GOLEM in the VM

For a quick developer run:

```powershell
python main.py
```

For a release-style local build:

```powershell
.\build_windows_installer.ps1
```

That produces:

- `dist\GOLEM\GOLEM.exe`
- `dist\GOLEM-Setup-<version>.exe`

## 5. Smoke-test the build

Use a clean VM profile and test these flows:

1. Launch `python main.py` or the bundled `GOLEM.exe`.
2. Complete onboarding.
3. Pick a watched folder and vault.
4. Create a small `.txt` file in the watched folder.
5. Confirm indexing and note creation.
6. Open the search popup with `Ctrl+Shift+Space`.
7. Verify the tray menu and quit path.

If you want a cleaner test, use `GOLEM_DATA_DIR` to point the app at a temp folder:

```powershell
$env:GOLEM_DATA_DIR = "$env:TEMP\golem-test-data"
python main.py
```

## 6. Build the final release artifacts

If you are shipping from the VM, use the release script:

```powershell
$env:GOLEM_VERSION = "2.0.1"
.\release_windows.ps1
```

If `GOLEM_VERSION` is not set, the scripts read `golem\constants.py`.

The release script copies the final artifacts into:

- `dist\releases\windows\GOLEM-<version>-windows.exe`
- `dist\releases\windows\GOLEM-<version>-windows-installer.exe`

## 7. Publish on GitHub

There are two ways to publish:

### Option A: Tag-driven release

```powershell
git add .
git commit -m "Release GOLEM 2.0.1"
git tag v2.0.1
git push origin main
git push origin v2.0.1
```

GitHub Actions will build the release and create the GitHub Release page.

### Option B: Manual GitHub Release

1. Build the artifacts locally with `.\release_windows.ps1`.
2. Upload the files from `dist\releases\windows\` to a new GitHub Release.
3. Attach the checksum file if you generate one.

## 8. How a user downloads and installs it

1. Open the GitHub **Releases** page.
2. Download `GOLEM-<version>-windows-installer.exe`.
3. Verify the file hash if a checksum file is published.
4. Run the installer.
5. Keep the default install location unless you have a reason to change it.
6. Launch GOLEM after install.

## 9. How a tester validates it

1. Open the installer from a clean Windows account if possible.
2. Install to the default location.
3. Confirm the Start Menu shortcut appears.
4. Confirm the Desktop shortcut appears if enabled.
5. Launch GOLEM and complete onboarding.
6. Drop a sample file into the watched folder.
7. Search for it and open it from the popup.
8. Uninstall from Windows Settings or with the uninstaller entry.

## 10. How to use it day to day

- Keep a watched folder for files you want indexed.
- Keep your Obsidian vault selected so notes land in the right place.
- Use `Ctrl+Shift+Space` to search without leaving your current app.
- Use the tray icon for re-scan, undo, logs, and quit.
- If you do not want cloud AI, choose Heuristic mode during onboarding.

## Notes

- Always test on a clean VM snapshot before publishing a public release.
- If the installer or app behaves oddly, check `golem.log` in the data directory.
- For the authoritative release process, see [`docs/RELEASE.md`](RELEASE.md).
