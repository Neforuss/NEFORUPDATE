# -*- mode: python ; coding: utf-8 -*-
# NEFORUPDATE folder build for the installer - made by Neforus (https://neforus.com).
# Same app as NEFORUPDATE.spec, but as a folder (dist\NEFORUPDATE-app\) instead of one self-unpacking
# .exe: installed copies start faster and don't unpack ~50 MB to a temp folder on every launch.
# Built by release.cmd; the installer (installer\neforupdate.iss) packages this folder.


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('licenses', 'licenses'), ('LICENSE', '.'),
           ('THIRD-PARTY-NOTICES.md', '.'), ('BRANDING.md', '.')],  # MIT + bundled-software notices
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
splash = Splash(
    'assets/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
    max_img_size=(1280, 720),  # show the full 720p splash (PyInstaller's default limit is 760x480)
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name='NEFORUPDATE',
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
    version='version_info.txt',
    icon=['assets/neforupdate.ico'],
    manifest='windows-manifest.xml',  # DPI-aware, so the splash isn't stretched on scaled displays
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NEFORUPDATE-app',
)
