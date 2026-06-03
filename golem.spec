# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).resolve()

datas = []
for folder in ("ui", "assets"):
    folder_path = ROOT / folder
    if folder_path.exists():
        datas.append((str(folder_path), folder))

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Hotkey backends. The runtime picks one of these based on what
        # the platform supports; both must be packaged.
        "keyboard",
        "pynput",
        "pynput.keyboard",
        # Tray icon. The runtime imports PIL lazily inside _build_icon_image.
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # Office / PDF extractors. openpyxl lazy-imports its cell writers,
        # so the module name alone is not enough on some PyInstaller
        # versions — listing the submodules is harmless and prevents
        # "ModuleNotFoundError" at runtime.
        "openpyxl",
        "openpyxl.cell",
        "openpyxl.cell._writer",
        "openpyxl.worksheet",
        "pypdf",
        "docx",
        # DPAPI / Windows API. ctypes.wintypes is a submodule that
        # PyInstaller's static analysis does not always pick up. On
        # non-Windows this import is a no-op (the code path is guarded
        # by ``if _is_windows()``), so the hidden import is harmless.
        "ctypes",
        "ctypes.wintypes",
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
