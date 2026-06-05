#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
# Target architecture: "x86_64" or "aarch64"
GOLEM_ARCH="${GOLEM_ARCH:-x86_64}"

if [[ "$GOLEM_ARCH" != "x86_64" && "$GOLEM_ARCH" != "aarch64" ]]; then
  echo "Error: GOLEM_ARCH must be 'x86_64' or 'aarch64' (got '$GOLEM_ARCH')." >&2
  exit 1
fi

echo "=== GOLEM Linux Build (arch=$GOLEM_ARCH) ==="

# Ensure Python is available
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: Python 3 not found. Set PYTHON_BIN or install Python 3.11+." >&2
  exit 1
fi

# Read APP_VERSION from constants
APP_VERSION="$(
  "$PYTHON_BIN" -c "import sys; sys.path.insert(0, '.'); from golem.constants import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "2.0.0"
)"

# Set up build venv
VENV="$ROOT/.venv-build"
PYBIN="$VENV/bin/python"

if [[ ! -x "$PYBIN" ]]; then
  echo "Creating build venv..."
  "$PYTHON_BIN" -m venv "$VENV"
  "$PYBIN" -m pip install --upgrade pip
  "$PYBIN" -m pip install -r requirements-build.txt
fi

# Step 1: Build the application bundle
echo "Step 1/4: Building application bundle ($GOLEM_ARCH)..."
# PyInstaller's target_arch is not used on Linux in the same way as macOS,
# but we set it for consistency. The built binary's arch matches the
# Python interpreter's arch.
GOLEM_PYI_ARCH="$GOLEM_ARCH" "$PYBIN" -m PyInstaller --noconfirm --clean golem.spec

APP_DIR="dist/GOLEM"
if [[ ! -d "$APP_DIR" ]]; then
  echo "Error: $APP_DIR was not created." >&2
  exit 1
fi

# Step 2: Create tar.gz
echo "Step 2/4: Creating tar.gz archive..."
ARCH_TAG="linux-${GOLEM_ARCH}"
TAR_GZ="dist/GOLEM-${APP_VERSION}-${ARCH_TAG}.tar.gz"
rm -f "$TAR_GZ"
tar -C "dist" -czf "$TAR_GZ" "GOLEM"
echo "Created: $TAR_GZ"

# Step 3: Create AppImage if tooling is available
echo "Step 3/4: Attempting AppImage creation..."
if command -v appimagetool >/dev/null 2>&1; then
  APPIMAGE_DIR="dist/GOLEM.AppDir"
  rm -rf "$APPIMAGE_DIR"
  mkdir -p "$APPIMAGE_DIR/usr/share/applications"
  mkdir -p "$APPIMAGE_DIR/usr/share/icons/hicolor/256x256/apps"
  mkdir -p "$APPIMAGE_DIR/usr/bin"

  cp -r "$APP_DIR"/* "$APPIMAGE_DIR/usr/bin/"

  if [[ -f "assets/golem.desktop" ]]; then
    cp assets/golem.desktop "$APPIMAGE_DIR/"
    cp assets/golem.desktop "$APPIMAGE_DIR/usr/share/applications/"
  fi

  cat > "$APPIMAGE_DIR/AppRun" << 'APPRUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/GOLEM" "$@"
APPRUN
  chmod +x "$APPIMAGE_DIR/AppRun"

  APPIMAGE_OUT="dist/GOLEM-${APP_VERSION}-${GOLEM_ARCH}.AppImage"
  appimagetool "$APPIMAGE_DIR" "$APPIMAGE_OUT" || \
    echo "Warning: appimagetool failed; AppImage not created." >&2
else
  echo "AppImage tooling not available (install appimagetool for AppImage support)."
fi

# Step 4: Create .deb package if dpkg-deb is available
echo "Step 4/4: Attempting .deb packaging..."
if command -v dpkg-deb >/dev/null 2>&1; then
  # Map GOLEM arch names to Debian package arch names
  case "$GOLEM_ARCH" in
    aarch64) DEB_ARCH="arm64" ;;
    x86_64)  DEB_ARCH="amd64" ;;
    *)       DEB_ARCH="$GOLEM_ARCH" ;;
  esac
  DEB_DIR="dist/golem_${APP_VERSION}_${DEB_ARCH}"
  rm -rf "$DEB_DIR"
  mkdir -p "$DEB_DIR/DEBIAN"
  mkdir -p "$DEB_DIR/usr/share/applications"
  mkdir -p "$DEB_DIR/usr/share/pixmaps"
  mkdir -p "$DEB_DIR/opt/golem"

  cat > "$DEB_DIR/DEBIAN/control" << CONTROL
Package: golem
Version: ${APP_VERSION}
Section: utils
Priority: optional
Architecture: ${DEB_ARCH}
Depends: libc6 (>= 2.31)
Maintainer: GOLEM Contributors
Description: Local-first AI file manager for Obsidian
 GOLEM watches a folder, extracts text from files, and organizes
 them into your Obsidian vault with AI-generated summaries and tags.
CONTROL

  cp -r "$APP_DIR"/* "$DEB_DIR/opt/golem/"

  if [[ -f "assets/golem.desktop" ]]; then
    sed 's|Exec=GOLEM|Exec=/opt/golem/GOLEM|g' "assets/golem.desktop" > "$DEB_DIR/usr/share/applications/golem.desktop"
  fi

  dpkg-deb --build "$DEB_DIR" "dist/golem_${APP_VERSION}_${DEB_ARCH}.deb"
  echo "Created: dist/golem_${APP_VERSION}_${DEB_ARCH}.deb"
else
  echo "dpkg-deb not available; .deb package not created."
fi

echo ""
echo "=== Build complete ==="
echo "Architecture: $GOLEM_ARCH"
echo "Archive:      $TAR_GZ"
ls -la "dist/"*"${GOLEM_ARCH}.AppImage" 2>/dev/null && echo "AppImage:     dist/GOLEM-${APP_VERSION}-${GOLEM_ARCH}.AppImage"
ls -la "dist/"*"${DEB_ARCH}.deb" 2>/dev/null && echo "Deb package:  dist/golem_${APP_VERSION}_${DEB_ARCH}.deb"
