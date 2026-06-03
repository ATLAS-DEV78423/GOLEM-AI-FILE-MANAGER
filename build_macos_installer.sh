#!/usr/bin/env bash
# Build the GOLEM macOS app bundle and (if hdiutil is present) a DMG.
# Uses a project-local venv so the build is reproducible and does not
# pollute the system Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-build"
PYTHON_BIN="$VENV/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  SYSTEM_PY="$(command -v python3 || true)"
  if [[ -z "$SYSTEM_PY" ]]; then
    echo "Python 3 is not installed. Install it via 'brew install python@3.11' and retry." >&2
    exit 1
  fi
  "$SYSTEM_PY" -m venv "$VENV"
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -r requirements.txt
  if [[ -f "$ROOT/requirements-build.txt" ]]; then
    "$PYTHON_BIN" -m pip install -r requirements-build.txt
  fi
fi

echo "Building GOLEM.app with $(basename "$PYTHON_BIN")"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean golem_macos.spec

APP_BUNDLE="dist/GOLEM.app"
DMG_PATH="dist/GOLEM-macOS.dmg"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "macOS app bundle was not created at $APP_BUNDLE" >&2
  exit 1
fi

if command -v hdiutil >/dev/null 2>&1; then
  rm -f "$DMG_PATH"
  hdiutil create -volname "GOLEM" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"
  echo "macOS installer created at $DMG_PATH"
else
  echo "hdiutil not found; leaving the app bundle at $APP_BUNDLE"
fi
