#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python is not installed or PYTHON_BIN is invalid. Run 'python3 -m pip install -r requirements.txt' first." >&2
  exit 1
fi

"$PYTHON_BIN" -m PyInstaller --noconfirm --clean golem_macos.spec

APP_BUNDLE="dist/GOLEM.app"
DMG_PATH="dist/GOLEM-macOS.dmg"

if [[ -d "$APP_BUNDLE" ]] && command -v hdiutil >/dev/null 2>&1; then
  rm -f "$DMG_PATH"
  hdiutil create -volname "GOLEM" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"
fi
