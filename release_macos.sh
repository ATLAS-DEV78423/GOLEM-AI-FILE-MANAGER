#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="${GOLEM_VERSION:-2.0.0}"
if [[ "$VERSION" == v* ]]; then
  VERSION="${VERSION#v}"
fi
DIST_DIR="$ROOT/dist"
APP_BUNDLE="$DIST_DIR/GOLEM.app"
DMG_PATH="$DIST_DIR/GOLEM-macOS.dmg"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python is not installed or PYTHON_BIN is invalid. Run 'python3 -m pip install -r requirements.txt' first." >&2
  exit 1
fi

echo "Building macOS app bundle for version $VERSION"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean golem_macos.spec

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "macOS app bundle was not created at $APP_BUNDLE" >&2
  exit 1
fi

if [[ "${GOLEM_SKIP_SIGNING:-0}" != "1" ]]; then
  : "${GOLEM_CODESIGN_IDENTITY:?Set GOLEM_CODESIGN_IDENTITY to a Developer ID Application identity}"
  codesign --force --deep --options runtime --timestamp --sign "$GOLEM_CODESIGN_IDENTITY" "$APP_BUNDLE"
fi

rm -f "$DMG_PATH"
hdiutil create -volname "GOLEM" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"

if [[ "${GOLEM_SKIP_SIGNING:-0}" != "1" ]]; then
  if [[ -n "${GOLEM_NOTARY_PROFILE:-}" ]]; then
    xcrun notarytool submit "$DMG_PATH" --keychain-profile "$GOLEM_NOTARY_PROFILE" --wait
  else
    : "${GOLEM_APPLE_ID:?Set GOLEM_APPLE_ID for notarization}"
    : "${GOLEM_APPLE_TEAM_ID:?Set GOLEM_APPLE_TEAM_ID for notarization}"
    : "${GOLEM_APPLE_APP_PASSWORD:?Set GOLEM_APPLE_APP_PASSWORD for notarization}"
    xcrun notarytool submit "$DMG_PATH" \
      --apple-id "$GOLEM_APPLE_ID" \
      --team-id "$GOLEM_APPLE_TEAM_ID" \
      --password "$GOLEM_APPLE_APP_PASSWORD" \
      --wait
  fi
  xcrun stapler staple "$APP_BUNDLE"
  xcrun stapler staple "$DMG_PATH"
fi

RELEASE_DIR="$DIST_DIR/releases/macos"
mkdir -p "$RELEASE_DIR"
VERSIONED_DMG="$RELEASE_DIR/GOLEM-$VERSION-macOS.dmg"
cp "$DMG_PATH" "$VERSIONED_DMG"

echo "macOS release artifact:"
echo "  $VERSIONED_DMG"
