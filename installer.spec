# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).resolve()
payload = ROOT / "dist" / "GOLEM"

datas = []
if payload.exists():
    datas.append((str(payload), "payload/GOLEM"))

a = Analysis(
    ["installer.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # tkinter is used by the GUI installer; required on every platform.
        "tkinter",
        # winreg is a stdlib Windows module. We list it conditionally
        # below in case this spec is ever built on a non-Windows host
        # (for shape verification, not for shipping). The import in
        # installer.py is itself guarded by ``if sys.platform == "win32"``.
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Conditional hidden import for winreg. PyInstaller does not allow
# ``hiddenimports`` to be a mutable list easily, so we patch the
# analysis object after the fact. The result is the same: winreg is
# included in the frozen binary only when it exists on the build host.
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
    name="GOLEM-Setup",
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
