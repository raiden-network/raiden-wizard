from eth_utils import to_checksum_address
from .addresses import mainnet, rinkeby, ropsten, kovan

GAS_LIMIT = 50000
NULL_WALLET_ADDRESS = to_checksum_address("0x0000000000000000000000000000000000000000")
NETWORK_ADDRESS_MODULES_BY_CHAIN_ID = {1: mainnet, 3: ropsten, 4: rinkeby, 42: kovan}
