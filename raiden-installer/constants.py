import pathlib


class ETHEREUM_CLIENTS:
    GETH = 'geth'
    PARITY = 'parity'


class PATHS:
    USR_BIN_DIR = pathlib.Path('/usr/local/bin')
    DEFAULT_INSTALL_DIR = pathlib.Path('/opt/raiden')


class VERSIONS:
    GETH = ''
    PARITY = ''
    RAIDEN = 'latest'


class URLS:
    GETH_BINARY = ''
    PARITY_BINARY = ''
    RAIDEN_SPACE = ''
