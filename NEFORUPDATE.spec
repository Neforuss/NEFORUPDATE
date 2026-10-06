# -*- mode: python ; coding: utf-8 -*-
# NEFORUPDATE build recipe - made by Neforus (https://neforus.com). Build with build.cmd.


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
    a.binaries,
    a.datas,
    splash,
    splash.binaries,
    [],
    name='NEFORUPDATE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
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
