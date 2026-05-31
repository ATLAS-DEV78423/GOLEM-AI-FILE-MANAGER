# Releases

## Windows

Use:

- [build_windows_installer.ps1](../build_windows_installer.ps1)
- [release_windows.ps1](../release_windows.ps1)

Expected artifacts:

- `dist/releases/windows/GOLEM-<version>-windows.exe`
- `dist/releases/windows/GOLEM-<version>-windows-installer.exe`

## macOS

Use:

- [build_macos_installer.sh](../build_macos_installer.sh)
- [release_macos.sh](../release_macos.sh)

Expected artifact:

- `dist/releases/macos/GOLEM-<version>-macOS.dmg`

## Notes

- Windows signing uses `signtool.exe` and the configured signing environment variables.
- macOS signing and notarization require Apple Developer credentials.
- The release checklist lives in [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).

