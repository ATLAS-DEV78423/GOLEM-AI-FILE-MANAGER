#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SIGN_IDENTITY="${SIGN_IDENTITY:-}"   # e.g. "Developer ID Application: Name (TEAMID)"
NOTARIZE="${NOTARIZE:-false}"
# Target architecture: "x86_64", "arm64", or "universal2"
GOLEM_ARCH="${GOLEM_ARCH:-}"

if [[ -n "$GOLEM_ARCH" && "$GOLEM_ARCH" != "x86_64" && "$GOLEM_ARCH" != "arm64" && "$GOLEM_ARCH" != "universal2" ]]; then
  echo "Error: GOLEM_ARCH must be 'x86_64', 'arm64', 'universal2', or empty (native)." >&2
  exit 1
fi

ARCH_DISPLAY="${GOLEM_ARCH:-native}"
echo "=== GOLEM macOS Build (arch=$ARCH_DISPLAY) ==="

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: Python not found. Set PYTHON_BIN or install Python 3.11+." >&2
  exit 1
fi

# Map PyInstaller target_arch (empty = native arch)
PYI_ARCH=""
case "$GOLEM_ARCH" in
  universal2) PYI_ARCH="universal2" ;;
  x86_64)     PYI_ARCH="x86_64" ;;
  arm64)      PYI_ARCH="arm64" ;;
esac

# Step 1: Build the app bundle
echo "Step 1/4: Building GOLEM.app (${PYI_ARCH:-native})..."
# Override target_arch in the spec file via env var that the spec reads
GOLEM_PYI_ARCH="$PYI_ARCH" "$PYTHON_BIN" -m PyInstaller --noconfirm --clean golem_macos.spec

APP_BUNDLE="dist/GOLEM.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Error: $APP_BUNDLE was not created." >&2
  exit 1
fi

# Verify architecture in the binary (not available for universal2 before signing)
if [[ "$GOLEM_ARCH" != "universal2" ]]; then
  echo "Binary architecture:"
  lipo -info "$APP_BUNDLE/Contents/MacOS/GOLEM" 2>/dev/null || file "$APP_BUNDLE/Contents/MacOS/GOLEM"
fi

# Step 2: Code sign if identity is provided
if [[ -n "$SIGN_IDENTITY" ]]; then
  echo "Step 2/4: Signing application bundle..."
  codesign --deep --force --verify --verbose --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
  codesign --verify --deep --strict "$APP_BUNDLE"
  echo "Signature verification passed."
fi

# Step 3: Create DMG
ARCH_TAG="${GOLEM_ARCH:-native}"
DMG_PATH="dist/GOLEM-macOS-${ARCH_TAG}.dmg"
echo "Step 3/4: Creating DMG at $DMG_PATH..."
rm -f "$DMG_PATH"
if command -v hdiutil >/dev/null 2>&1; then
  hdiutil create -volname "GOLEM" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"
  echo "DMG created: $DMG_PATH"
else
  echo "Warning: hdiutil not found; skipping DMG creation." >&2
fi

# Step 4: Notarize (optional)
if [[ "$NOTARIZE" == "true" ]] && [[ -n "$SIGN_IDENTITY" ]]; then
  if [[ -z "${APPLE_ID:-}" || -z "${APPLE_PASSWORD:-}" ]]; then
    echo "Error: APPLE_ID and APPLE_PASSWORD must be set for notarization." >&2
    exit 1
  fi
  echo "Step 4/4: Notarizing..."
  ditto -c -k --keepParent "$APP_BUNDLE" "dist/GOLEM-notarize.zip"
  TEAM_ID="$(echo "$SIGN_IDENTITY" | sed -n 's/.*(\(.*\))/\1/p')"
  xcrun notarytool submit "dist/GOLEM-notarize.zip" --wait \
    --apple-id "${APPLE_ID}" --team-id "${TEAM_ID}" --password "${APPLE_PASSWORD}"
  rm -f "dist/GOLEM-notarize.zip"
  xcrun stapler staple "$APP_BUNDLE"
  echo "Notarization complete."
fi

echo ""
echo "=== Build complete ==="
echo "Architecture: ${ARCH_TAG}"
echo "Application:  $APP_BUNDLE"
echo "Disk image:   ${DMG_PATH:-N/A}"
