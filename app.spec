# -*- mode: python -*-

import os
import sys

block_cipher = None

PWD = os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(sys.argv[-1])))
WEBAPP_FOLDER = os.path.abspath(
    os.path.join(PWD, "..", "..", "raiden_installer", "web")
)
HOOKS_FOLDER = os.path.join(PWD, "hooks")

a = Analysis(
    [os.path.join(WEBAPP_FOLDER, "app.py")],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(WEBAPP_FOLDER, "templates"), "templates"),
        (os.path.join(WEBAPP_FOLDER, "static"), "static"),
    ],
    hiddenimports=[
        "appdirs",
        "packaging",
        "packaging.version",
        "packaging.specifiers",
        "packaging.requirements",
    ],
    hookspath=[HOOKS_FOLDER],
    runtime_hooks=[os.path.join(HOOKS_FOLDER, "runtime_raiden_contracts.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
    name="raiden_test_launcher",
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,
)
