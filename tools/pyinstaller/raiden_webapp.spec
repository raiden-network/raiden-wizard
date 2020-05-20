# -*- mode: python -*-

import distutils
import os
import sys

try:
    if distutils.distutils_path.endswith("__init__.py"):
        distutils.distutils_path = os.path.dirname(distutils.distutils_path)
except AttributeError:
    pass


block_cipher = None

PWD = os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(sys.argv[-1])))
ROOT_FOLDER = os.path.abspath(os.path.join(PWD, "..", ".."))
RESOURCE_FOLDER = os.path.abspath(os.path.join(ROOT_FOLDER, "resources"))

HOOKS_FOLDER = os.path.join(PWD, "hooks")

a = Analysis(
    [os.path.join(ROOT_FOLDER, "raiden_installer", "web.py")],
    pathex=[os.path.join(ROOT_FOLDER, "raiden_installer")],
    binaries=[],
    datas=[(RESOURCE_FOLDER, "resources")],
    hiddenimports=[
        "appdirs",
        "cytoolz._signatures",
        "Crypto.Cipher._mode_ecb",
        "eth_utils",
        "eth_keyfile",
        "eth_abi",
        "packaging",
        "packaging.version",
        "packaging.specifiers",
        "packaging.requirements",
        "pkg_resources.py2_warn",
        "web3",
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
    name="raiden_wizard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,
)

