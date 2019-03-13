import pathlib
import sys


ARCHIVE_EXT = 'zip' if sys.platform == 'darwin' else 'tar.gz'


class PATHS:
    USR_BIN_DIR = pathlib.Path('/usr/local/bin')
    DEFAULT_INSTALL_DIR = pathlib.Path('/opt/raiden')


class RAIDEN_META:
    NAME = 'raiden'
    VERSION = 'v0.100.2'
    BINARY_NAME = f'raiden-{VERSION}'
    ARCH = 'macOS' if sys.platform == 'darwin' else 'linux'
    ARCHIVE = f'{BINARY_NAME}-{ARCH}-x86_64.{ARCHIVE_EXT}'
    DOWNLOAD_URL = f'https://github.com/raiden-network/raiden/releases/download/{VERSION}/{ARCHIVE}'


class GETH_META:
    NAME = 'geth'
    VERSION = '1.8.23'
    ARCH = sys.platform
    COMMIT = 'c9427004'
    DOWNLOAD_URL = f'https://gethstore.blob.core.windows.net/builds/geth-{ARCH}-{VERSION}-{COMMIT}.tar.gz'
    SIGNATURE = f'{DOWNLOAD_URL}.asc'
    BIN_PATH = PATHS.USR_BIN_DIR.joinpath(NAME)
    KEYSTORE_PATH = pathlib.Path.home().joinpath('.ethereum')


class PARITY_META:
    NAME = 'parity'
    VERSION = 'v2.4.0'
    ARCH = 'apple-darwin' if sys.platform == 'darwin' else 'unknown-linux-gnu'
    DOWNLOAD_URL = f'https://releases.parity.io/ethereum/{VERSION}/x86_64-{ARCH}/parity'
    BIN_PATH = PATHS.USR_BIN_DIR.joinpath(NAME)
    KEYSTORE_PATH = pathlib.Path.home().joinpath('.local', 'share', 'io.parity.ethereum', 'keys')
