# Expected Raiden client default path values.
RAIDEN_INSTALL_PATH = '/opt/raiden'
DEFAULT_BIN_PATH = f'{RAIDEN_INSTALL_PATH}/bin'
RAIDEN_BINARY = DEFAULT_BIN_PATH + '/raiden'
RAIDEN_SPACE = 'https://raiden-nightlies.ams3.digitaloceanspaces.com/'
# Raiden 'custom' paths, emulating user input during install steps.
CUSTOM_BIN_PATH = '/opt/testing/bin'


# Eth Clients
PARITY = 'parity'
GETH = 'geth'

# Path to our local dummy client. Append the client name you want the dummy for.
LOCAL_CLIENT_PATH = './tests/acceptance-tests/bin'
# URL to our dummy remote Node. Append client name as endpoint during testing,
# i.e. if you want to test raiden with parity use ${REMOTE_CLIENT}/parity.
REMOTE_CLIENT_PATH = 'http://localhost:3333'

# Test Networks
GOERLI = 'goerli'
RINKEBY = 'rinkeby'
ROPSTEN = 'ROPSTEN'
KOVAN = 'kovan'


# Infura variables for testing
VALID_INFURA_ID = ''
INVALID_INFURE_ID = ''


# Generic Test variables for easier readablity in test cases.
SUCCESS = True
FAILURE = False
