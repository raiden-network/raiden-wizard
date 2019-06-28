import sys
from raiden_contracts.constants import GAS_REQUIRED_FOR_UDC_DEPOSIT


PLATFORM = 'macOS' if sys.platform == 'darwin'  else 'linux'

DEST_DIR = '/Users/taleldayekh/desktop/installer'


# Constants for PFS and Monitoring funding
GAS_PRICE = 2_000_000_000
GAS_MINT = 70_000
GAS_APPROVE = 70_000
GAS_DEPOSIT = GAS_REQUIRED_FOR_UDC_DEPOSIT * 2

TOKEN_AMOUNT = 10 ** 18