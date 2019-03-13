import pathlib
import sys


if sys.platform == 'darwin':
    ARCHIVE_EXT = 'zip'
    PLATFORM = 'macOS'
else:
    ARCHIVE_EXT = 'tar.gz'
    PLATFORM = 'linux'


class PATHS:
    USR_BIN_DIR = pathlib.Path('/usr/local/bin')
    DEFAULT_INSTALL_DIR = pathlib.Path('/opt/raiden')


class RAIDEN_META:
    NAME = 'raiden'
    VERSION = 'v0.100.2'
    BINARY_NAME = f'raiden-{VERSION}'
    ARCHIVE = f'{BINARY_NAME}-{PLATFORM}-x86_64.{ARCHIVE_EXT}'
    DOWNLOAD_URL = f'https://github.com/raiden-network/raiden/releases/download/{VERSION}/{ARCHIVE}'


class GETH_META:
    NAME = 'geth'
    VERSION = '1.8.23'
    FLAVOR = sys.platform
    COMMIT = 'c9427004'
    DOWNLOAD_URL = f'https://gethstore.blob.core.windows.net/builds/geth-{FLAVOR}-{VERSION}-{COMMIT}.tar.gz'
    SIGNATURE = f'{DOWNLOAD_URL}.asc'
    BIN_PATH = PATHS.USR_BIN_DIR.joinpath(NAME)


class PARITY_META:
    NAME = 'parity'
    VERSION = 'v2.4.0'
    FLAVOR = 'apple-darwin' if sys.platform == 'darwin' else 'unknown-linux-gnu'
    DOWNLOAD_URL = f'https://releases.parity.io/ethereum/{VERSION}/x86_64-{FLAVOR}/parity'
    BIN_PATH = PATHS.USR_BIN_DIR.joinpath(NAME)
