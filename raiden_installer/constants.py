import sys
from pathlib import Path
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME


"""
Raiden installer uses the XDG Base Directory standard for
storing its files. XDG_DATA_HOME is used for storing user
keystore files whilst XDG_CONFIG_HOME stores config files
necessary for initializing Raiden.
"""
BINARY_DIR = Path("/usr/local/bin")
CONFIG_DIR = Path(XDG_CONFIG_HOME).joinpath("Raiden")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
KEYSTORE_DIR = Path(XDG_DATA_HOME).joinpath("Raiden")
KEYSTORE_DIR.mkdir(parents=True, exist_ok=True)


PLATFORM = "macOS" if sys.platform == "darwin" else "linux"


"""
Constants for interacting with smart contracts used
for funding the Pathfinding and Monitoring services.
"""
TOKEN_AMOUNT = 10 ** 18
GAS_PRICE = 2_000_000_000

GAS_REQUIRED_FOR_MINT = 70_000
GAS_REQUIRED_FOR_APPROVE = 70_000
GAS_REQUIRED_FOR_DEPOSIT = 200_000
