# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


launcher_dir = Path(SPECPATH)

a = Analysis(
    [str(launcher_dir / "app.py")],
    pathex=[str(launcher_dir)],
    binaries=[],
    datas=[(str(launcher_dir / "assets"), "assets"), (str(launcher_dir / "games.json"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cruis'n Xtreme",
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
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Cruis'n Xtreme",
)
app = BUNDLE(
    coll,
    name="Cruis'n Xtreme.app",
    icon=None,
    bundle_identifier="org.cruisnxtreme.launcher",
    version="0.1",
    info_plist={
        "CFBundleDisplayName": "Cruis'n Xtreme",
        "CFBundleName": "Cruis'n Xtreme",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
