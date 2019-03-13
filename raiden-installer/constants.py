import pathlib
import sys


if sys.platform == 'darwin':
    ARCHIVE_EXT = 'zip'
    PLATFORM = 'macOS'
else:
    ARCHIVE_EXT = 'tar.gz'
    PLATFORM = 'linux'


class RAIDEN_META:
    NAME = 'raiden'
    VERSION = 'v0.100.2'
    BINARY_NAME = f'raiden-{VERSION}'
    ARCHIVE = f'{BINARY_NAME}-{PLATFORM}-x86_64.{ARCHIVE_EXT}'
    DOWNLOAD_URL = f'https://github.com/raiden-network/raiden/releases/download/{VERSION}/{ARCHIVE}'


class GETH_META:
    NAME = 'geth'
    VERSION = ''
    BINARY = ''
    DOWNLOAD_URL = ''


class PARITY_META:
    NAME = 'parity'
    VERSION = ''
    BINARY = ''
    DOWNLOAD_URL = ''


class PATHS:
    USR_BIN_DIR = pathlib.Path('/usr/local/bin')
    DEFAULT_INSTALL_DIR = pathlib.Path('/opt/raiden')



