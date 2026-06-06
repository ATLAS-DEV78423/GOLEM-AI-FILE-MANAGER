# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the GOLEM WebView launcher.

This builds the WebView-based front-end (the new v2.1 UI) as a
standalone executable. The installer embeds this bundle as its payload.

Usage::

    pyinstaller golem_webview.spec --noconfirm --clean

Requires: pywebview, keyboard, and all GOLEM dependencies.
"""
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve()

# ── Collect all UI files (index.html, style.css, app.js) ────────
datas = []
for folder in ("ui", "assets"):
    folder_path = ROOT / folder
    if folder_path.exists():
        datas.append((str(folder_path), folder))

# ── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    ["golem_webview.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # ── GOLEM backend ──
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

        # ── WebView ──
        "webview",
        "webview.platforms",
        "webview.platforms.win32_edge",
        "webview.platforms.cocoa",
        "webview.platforms.gtk",
        "webview.platforms.gtk3",
        "webview.util",

        # ── Hotkey ──
        "keyboard",
        "pynput",
        "pynput.keyboard",

        # ── LLM Providers ──
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.primitives",
        "cffi",
        "cffi.api",
        "cffi.cparser",

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

        # ── Sentence embeddings ──
        "sentence_transformers",
        "torch",
        "torch.nn",
        "transformers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# ── Fix winreg conditional import ────────────────────────────────
import importlib.util as _importlib_util
if _importlib_util.find_spec("winreg") is not None:
    a.hiddenimports.append("winreg")

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
