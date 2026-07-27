# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
import tomllib

from PyInstaller.utils.hooks import collect_all


PROGRAM_VERSION = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]


tkinterdnd2_datas, tkinterdnd2_binaries, tkinterdnd2_hiddenimports = collect_all(
    "tkinterdnd2"
)

analysis = Analysis(
    ["streckenbuch_gui.py"],
    pathex=[],
    binaries=tkinterdnd2_binaries,
    datas=tkinterdnd2_datas,
    hiddenimports=tkinterdnd2_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

if sys.platform == "darwin":
    executable = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="StreckenbuchExport",
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
    collected = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=True,
        name="StreckenbuchExport",
    )
    application = BUNDLE(
        collected,
        name="StreckenbuchExport.app",
        icon=None,
        bundle_identifier="de.streckenbuch.export",
        version=PROGRAM_VERSION,
        info_plist={
            "CFBundleDisplayName": "Streckenbuch Export",
            "CFBundleShortVersionString": PROGRAM_VERSION,
            "NSHighResolutionCapable": True,
        },
    )
else:
    executable = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="StreckenbuchExport",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
    )
