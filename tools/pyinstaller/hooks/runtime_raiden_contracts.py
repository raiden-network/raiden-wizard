import sys
from pathlib import Path
from raiden_contracts import contract_manager


base_path = Path(sys._MEIPASS)
contract_manager._BASE = base_path
