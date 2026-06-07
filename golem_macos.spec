# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for GOLEM v2.1 — macOS WebView-based launcher.

Targets golem_webview.py (the new PyWebView front-end) instead of the
legacy main.py (Tkinter).
"""
from pathlib import Path
import os
import sys

block_cipher = None

ROOT = Path(SPECPATH).resolve()

datas = []
for folder in ("ui", "assets"):
    folder_path = ROOT / folder
    if folder_path.exists():
        datas.append((str(folder_path), folder))

a = Analysis(
    ["golem_webview.py"],  # v2.1 entry point
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # ── GOLEM core ──
        "golem",
        "golem.ai",
        "golem.app",
        "golem.chunker",
        "golem.config",
        "golem.constants",
        "golem.embeddings",
        "golem.errors",
        "golem.extractor",
        "golem.hybrid_search",
        "golem.indexer",
        "golem.legal",
        "golem.organizer",
        "golem.scanner",
        "golem.search",
        "golem.summarizer",
        "golem.undo",
        "golem.utils",
        "golem.vault_writer",
        "golem.vector_store",
        "golem.watcher",
        "golem.watcher_events",

        # ── PyWebView v6.x (all sub-modules) ──
        "webview",
        "webview._version",
        "webview.errors",
        "webview.event",
        "webview.guilib",
        "webview.http",
        "webview.localization",
        "webview.menu",
        "webview.models",
        "webview.platforms",
        "webview.platforms.cocoa",
        "webview.screen",
        "webview.state",
        "webview.util",
        "webview.window",

        # ── pywebview runtime dependency ──
        "proxy_tools",

        # ── Hotkey ──
        "keyboard",
        "pynput",
        "pynput.keyboard",

        # ── Tray (legacy, kept for packaging test) ──
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",

        # ── Cryptography ──
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.primitives",
        "cffi",

        # ── File extraction ──
        "openpyxl",
        "openpyxl.cell",
        "openpyxl.cell._writer",
        "openpyxl.worksheet",
        "pypdf",
        "docx",

        # ── Security ──
        "defusedxml",
        "defusedxml.ElementTree",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Read target architecture from environment (set by build_macos.sh).
# Values: "x86_64", "arm64", "universal2", or None (native).
_pyi_arch = os.environ.get("GOLEM_PYI_ARCH") or None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GOLEM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_pyi_arch,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GOLEM",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GOLEM.app",
        icon=None,
        bundle_identifier="com.golem.desktop",
        info_plist={
            "CFBundleDisplayName": "GOLEM",
            "CFBundleName": "GOLEM",
            "CFBundleShortVersionString": "2.1.0",
            "CFBundleVersion": "2.1.0",
            "NSHighResolutionCapable": True,
            # Include both architectures in the bundle metadata
            "CFBundleSupportedPlatforms": ["MacOSX"],
        },
    )
