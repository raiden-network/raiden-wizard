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
from eth_utils import to_canonical_address, to_checksum_address
from raiden.accounts import InvalidAccountFile
from web3 import Web3

from raiden_installer import log
from raiden_installer.tokens import ETH, TokenAmount, Wei


def make_random_string(length=32):
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


class Account:
    DEFAULT_KEYSTORE_FOLDER: Optional[Path] = None

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

    def get_ethereum_balance(self, w3) -> TokenAmount:
        return TokenAmount(Wei(w3.eth.getBalance(self.address)), ETH)

    def wait_for_ethereum_funds(
        self, w3: Web3, expected_amount: TokenAmount, timeout: int = 300
    ) -> TokenAmount:
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

    @classmethod
    def find_keystore_file_path(cls, address, keystore_path):

        try:
            files = os.listdir(keystore_path)
        except OSError as ex:
            msg = "Unable to list the specified directory"
            log.error("OsError", msg=msg, path=keystore_path, ex=ex)
            return

        for f in files:
            full_path = keystore_path.joinpath(f)
            if full_path.is_file():
                try:
                    file_content = full_path.read_text()
                    data = json.loads(file_content)
                    if not isinstance(data, dict) or "address" not in data:
                        # we expect a dict in specific format.
                        # Anything else is not a keyfile
                        raise InvalidAccountFile(f"Invalid keystore file {full_path}")
                    address_from_file = to_checksum_address(to_canonical_address(data["address"]))
                    if address_from_file == address:
                        return Path(full_path)
                except OSError as ex:
                    msg = "Can not read account file (errno=%s)" % ex.errno
                    log.warning(msg, path=full_path, ex=ex)
                except (
                    json.JSONDecodeError,
                    KeyError,
                    UnicodeDecodeError,
                    InvalidAccountFile,
                ) as ex:
                    # Invalid file - skip
                    if f.startswith("UTC--"):
                        # Should be a valid account file - warn user
                        msg = "Invalid account file"
                        if isinstance(ex, json.decoder.JSONDecodeError):
                            msg = "The account file is not valid JSON format"
                        log.warning(msg, path=full_path, ex=ex)
