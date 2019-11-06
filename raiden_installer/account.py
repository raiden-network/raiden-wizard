import datetime
import glob
import json
import os
import random
import string
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_utils import to_checksum_address
from web3 import Web3

from raiden_installer import log
from raiden_installer.tokens import EthereumAmount, Wei


def make_random_string(length=32):
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


class Account:
    DEFAULT_KEYSTORE_FOLDER = None

    def __init__(self, keystore_file_path: Path, passphrase: Optional[str] = None):
        self.passphrase = passphrase
        self.keystore_file_path = Path(keystore_file_path)
        self.content = self._get_content()

    def _get_content(self):
        if self.keystore_file_path.exists():
            with self.keystore_file_path.open() as f:
                return json.load(f)
        return None

    @property
    def private_key(self):
        if not self.passphrase:
            raise ValueError("Passphrase is not known, can not get private key")

        return decode_keyfile_json(self.content, self.passphrase.encode())

    @property
    def address(self):
        return to_checksum_address(self.content.get("address"))

    def get_ethereum_balance(self, w3) -> EthereumAmount:
        return EthereumAmount(Wei(w3.eth.getBalance(self.address)))

    def wait_for_ethereum_funds(
        self, w3: Web3, expected_amount: EthereumAmount, timeout: int = 300
    ) -> EthereumAmount:
        time_remaining = timeout
        POLLING_INTERVAL = 1
        balance = self.get_ethereum_balance(w3)
        while balance < expected_amount and time_remaining > 0:
            balance = self.get_ethereum_balance(w3)
            time.sleep(POLLING_INTERVAL)
            time_remaining -= POLLING_INTERVAL
        log.debug(f"Balance is {balance}")
        return balance

    def check_passphrase(self, passphrase):
        try:
            decode_keyfile_json(self.content, passphrase.encode())
            return True
        except Exception:
            return False

    def unlock(self, passphrase):
        if self.check_passphrase(passphrase):
            self.passphrase = passphrase
        else:
            raise ValueError("Invalid Passphrase")

    @classmethod
    def generate_private_key(cls):
        return os.urandom(32)

    @classmethod
    def create(cls, passphrase=None):
        if passphrase is None:
            passphrase = make_random_string()

        time_stamp = (
            datetime.datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
        )
        uid = uuid.uuid4()

        keystore_file_path = Path(cls.find_keystore_folder_path()).joinpath(
            f"UTC--{time_stamp}Z--{uid}"
        )

        keystore_folder_path = Path(keystore_file_path).parent
        keystore_folder_path.mkdir(parents=True, exist_ok=True)

        with keystore_file_path.open("w") as keyfile:
            private_key = cls.generate_private_key()
            json.dump(create_keyfile_json(private_key, passphrase.encode()), keyfile)

        return cls(keystore_file_path, passphrase=passphrase)

    @classmethod
    def find_keystore_folder_path(cls) -> Path:
        if cls.DEFAULT_KEYSTORE_FOLDER:
            return cls.DEFAULT_KEYSTORE_FOLDER

        home = Path.home()

        if sys.platform == "darwin":
            return home.joinpath("Library", "Ethereum", "keystore")
        elif sys.platform in ("win32", "cygwin"):
            return home.joinpath("AppData", "Roaming", "Ethereum", "keystore")
        elif os.name == "posix":
            return home.joinpath(".ethereum", "keystore")
        else:
            raise RuntimeError("Unsupported Operating System")

    @classmethod
    def get_user_accounts(cls):
        keystore_glob = glob.glob(str(cls.find_keystore_folder_path().joinpath("UTC--*")))
        return [cls(keystore_file_path=Path(f)) for f in keystore_glob]
