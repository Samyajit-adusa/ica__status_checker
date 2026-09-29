# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import playwright
from PyInstaller.building.datastruct import Tree


PLAYWRIGHT_BROWSERS_DIR = Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('inputs.txt', '.')],
    hiddenimports=[],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += Tree(str(PLAYWRIGHT_BROWSERS_DIR), prefix='browsers')
pyz = PYZ(a.pure)

folder_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ica_automation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    folder_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ica_automation',
)

bridge_exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ica_automation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
