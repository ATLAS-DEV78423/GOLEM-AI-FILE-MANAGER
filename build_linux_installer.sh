#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python is not installed or PYTHON_BIN is invalid. Run 'python3 -m pip install -r requirements.txt' first." >&2
  exit 1
fi

VENV="$ROOT/.venv-build"
PYBIN="$VENV/bin/python"

if [[ ! -x "$PYBIN" ]]; then
  SYSTEM_PY="$(command -v python3 || true)"
  if [[ -z "$SYSTEM_PY" ]]; then
    echo "Python 3 is not installed. Install it and retry." >&2
    exit 1
  fi
  "$SYSTEM_PY" -m venv "$VENV"
  "$PYBIN" -m pip install --upgrade pip
  "$PYBIN" -m pip install -r requirements.txt
  if [[ -f "$ROOT/requirements-build.txt" ]]; then
    "$PYBIN" -m pip install -r requirements-build.txt
  fi
fi

echo "Building GOLEM with $(basename "$PYBIN")"
"$PYBIN" -m PyInstaller --noconfirm --clean golem.spec

APP_DIR="dist/GOLEM"
APP_TGZ="dist/GOLEM-linux.tar.gz"

if [[ -d "$APP_DIR" ]]; then
  rm -f "$APP_TGZ"
  tar -C "$APP_DIR" -czf "$APP_TGZ" .
  echo "Packaged one-folder app at $APP_TGZ"
else
  echo "Expected app directory $APP_DIR not found" >&2
  exit 1
fi

# Try to create an AppImage if appimagetool is available
if command -v appimagetool >/dev/null 2>&1; then
  echo "Creating AppImage (requires linuxdeploy/AppImage tooling)"
  # Prepare AppDir structure
  APPIMAGE_DIR="dist/GOLEM.AppDir"
  rm -rf "$APPIMAGE_DIR"
  mkdir -p "$APPIMAGE_DIR/usr/bin"
  cp -r "$APP_DIR"/* "$APPIMAGE_DIR/usr/bin/"
  # Minimal desktop integration (optional)
  if [[ -f "assets/golem.desktop" ]]; then
    mkdir -p "$APPIMAGE_DIR/usr/share/applications"
    cp assets/golem.desktop "$APPIMAGE_DIR/usr/share/applications/"
  fi
  appimagetool "$APPIMAGE_DIR" dist || echo "appimagetool failed; AppImage not created"
fi

echo "Linux build complete. Artifacts in dist/."
