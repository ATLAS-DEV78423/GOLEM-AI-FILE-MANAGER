# GOLEM Release Checklist

## Before You Start
- Set the release version with `GOLEM_VERSION`.
- Prepare Windows signing credentials or certificates.
- Prepare Apple Developer signing and notarization credentials for macOS.

## Windows Release
1. Run `.\release_windows.ps1`.
2. Set one of these signing configurations:
   - `GOLEM_SIGN_PFX_PATH` and `GOLEM_SIGN_PFX_PASSWORD`
   - `GOLEM_SIGN_CERT_SHA1`
3. Optional signing overrides:
   - `GOLEM_SIGN_TIMESTAMP_URL`
   - `GOLEM_SKIP_SIGNING=1` for local unsigned testing only
4. Confirm these artifacts exist:
   - `dist\releases\windows\GOLEM-<version>-windows.exe`
   - `dist\releases\windows\GOLEM-<version>-windows-installer.exe`

## macOS Release
1. Run `./release_macos.sh` on macOS.
2. Set `GOLEM_CODESIGN_IDENTITY` to a Developer ID Application identity.
3. For notarization, set either:
   - `GOLEM_NOTARY_PROFILE`
   - `GOLEM_APPLE_ID`, `GOLEM_APPLE_TEAM_ID`, and `GOLEM_APPLE_APP_PASSWORD`
4. Optional local-only override:
   - `GOLEM_SKIP_SIGNING=1`
5. Confirm this artifact exists:
   - `dist/releases/macos/GOLEM-<version>-macOS.dmg`

## Final Checks
- Install the Windows artifact on a clean Windows machine.
- Install the macOS DMG on a clean macOS machine.
- Verify the app launches, opens files, and writes notes correctly.
- Archive the signed release artifacts before publishing.
