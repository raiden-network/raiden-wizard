# -*- mode: python -*-

block_cipher = None


a = Analysis(['installer_server.py'],
             pathex=[],
             binaries=[],
             datas=[('templates', 'templates'), ('static', 'static')],
             hiddenimports=[],
             hookspath=['pyinstaller_hooks'],
             runtime_hooks=['pyinstaller_hooks/runtime_raiden_contracts.py'],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='installer_server',
          debug=True,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True )
