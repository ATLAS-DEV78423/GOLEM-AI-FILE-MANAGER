# Release Process

This document describes how a release is built, signed, and published.
Only the maintainer needs the secrets below; everyone else can build
unsigned artifacts locally for testing.

## Triggering a release

1. Bump `APP_VERSION` in `golem/constants.py` to the new version
   (e.g. `"2.1.0"`).
2. Update `CHANGELOG.md` with the release notes.
3. Push a `v2.1.0` tag:
   ```sh
   git tag v2.1.0
   git push origin v2.1.0
   ```
4. The `release` workflow in `.github/workflows/release.yml` runs.

## What the workflow does

1. `build-windows` job (windows-latest)
   - Sets up Python 3.11.
   - Installs `requirements.txt` + `requirements-build.txt`.
   - Runs `release_windows.ps1` which:
     - Calls `build_windows_installer.ps1` (PyInstaller onedir build).
     - Optionally signs `GOLEM.exe` and `GOLEM-Setup.exe` with
       `signtool.exe`.
     - Copies the artifacts to `dist/releases/windows/` with the
       version baked into the filename.
2. `build-macos` job (macos-latest)
   - Sets up Python 3.11.
   - Installs dependencies.
   - Runs `release_macos.sh` which:
     - Calls `build_macos_installer.sh` (PyInstaller .app build).
     - Optionally signs the .app with `codesign`.
     - Creates a `.dmg` with `hdiutil`.
3. `publish-release` job (ubuntu-latest)
   - Downloads the Windows and macOS artifacts.
   - Generates `SHA256SUMS.txt`.
   - Creates a source tarball via `git archive`.
   - Generates an SPDX SBOM via `anchore/sbom-action@v0`.
   - Creates a GitHub Release via `softprops/action-gh-release@v2`.
   - If the workflow was triggered by `workflow_dispatch`, the release
     is created as a draft for the maintainer to publish.

## Code signing secrets

The workflow signs artifacts only when the corresponding secrets are
configured. Without secrets, builds are produced but **not signed**.

### Windows

Set these repository secrets (Settings -> Secrets and variables ->
Actions):

| Secret | Required? | What it is |
|---|---|---|
| `GOLEM_SIGN_PFX_PATH` | One of two | Path on the runner to a code-signing `.pfx` (or `.p12`) |
| `GOLEM_SIGN_PFX_PASSWORD` | If PFX | The PFX's password |
| `GOLEM_SIGN_CERT_SHA1` | Alternative | Thumbprint of a cert in the runner's `CurrentUser\My` store |
| `GOLEM_SIGN_TIMESTAMP_URL` | Optional | Defaults to `http://timestamp.digicert.com` |

The `release_windows.ps1` script picks the path. Either provide a
PFX file at `GOLEM_SIGN_PFX_PATH`, or pre-install the certificate on
the runner and reference it by SHA1.

### macOS

| Secret | Required? | What it is |
|---|---|---|
| `MACOS_CERT_P12_BASE64` | For signing | Base64 of the Developer ID .p12 |
| `MACOS_CERT_PASSWORD` | For signing | Password for the .p12 |
| `MACOS_KEYCHAIN_PASSWORD` | For signing | Password for the temporary keychain |
| `APPLE_ID` | For notarization | Apple ID used to submit for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | For notarization | App-specific password |
| `APPLE_TEAM_ID` | For notarization | Apple Developer Team ID |

If `MACOS_CERT_P12_BASE64` is empty, the build script falls back to
ad-hoc signing (`codesign --sign -`) which is suitable for local
testing only — Gatekeeper will block the .app on a real user's
machine.

## Manual dry-run

To dry-run the release job's outputs locally:

```sh
# After a successful build on Windows or macOS:
cd dist/releases
find . -type f \( -name "*.exe" -o -name "*.dmg" -o -name "*.zip" -o -name "*.tar.gz" \) -exec sha256sum {} \; > SHA256SUMS.txt
# Inspect SHA256SUMS.txt, then create the source tarball:
VERSION=2.1.0
git archive --format=tar.gz --prefix="GOLEM-${VERSION}/" -o "GOLEM-${VERSION}-source.tar.gz" HEAD
```

The CI's `publish-release` job runs these exact commands. If they
succeed locally, CI will succeed for the same inputs.

## After release

1. Smoke test the Windows installer on a clean Windows VM.
2. Smoke test the macOS DMG on a clean macOS VM.
3. Verify the GitHub Release page has all artifacts and `SHA256SUMS.txt`.
4. Announce (Reddit, mailing list, etc.).
