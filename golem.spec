# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for GOLEM v2.1 — WebView-based launcher.

Targets golem_webview.py (the new PyWebView front-end) instead of the
legacy main.py (Tkinter). The UI files in ``ui/`` are bundled as data.
"""
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve()

# ── Bundle ui/ and assets/ directories ───────────────────────────
datas = []
for folder in ("ui", "assets"):
    folder_path = ROOT / folder
    if folder_path.exists():
        datas.append((str(folder_path), folder))

# ── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    ["golem_webview.py"],                          # <-- v2.1 entry point
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # ── GOLEM core (all modules) ──
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
        "webview.platforms.edgechromium",
        "webview.platforms.gtk",
        "webview.platforms.mshtml",
        "webview.platforms.qt",
        "webview.platforms.winforms",
        "webview.platforms.win32",
        "webview.screen",
        "webview.state",
        "webview.util",
        "webview.window",

        # ── pywebview runtime dependency ──
        "proxy_tools",

        # ── Hotkey backends ──
        "keyboard",
        "pynput",
        "pynput.keyboard",
        "pynput._util",
        "pynput._util.win32",

        # ── Cryptography ──
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.primitives",
        "cffi",
        "cffi.api",
        "cffi.cparser",

        # ── Tray (legacy, kept for packaging test) ──
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",

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

        # ── Windows ──
        "ctypes",
        "ctypes.wintypes",
        "winreg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
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
    target_arch=None,
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
