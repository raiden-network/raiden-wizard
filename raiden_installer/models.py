import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
import uuid
from typing import Optional

import requests
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from raiden_contracts.constants import CONTRACT_CUSTOM_TOKEN
from xdg import XDG_DATA_HOME


class Account:
    KEYSTORE_FOLDER = XDG_DATA_HOME

    def __init__(self, keystore_file_path: Path, passphrase: Optional[str] = None):
        self.passphrase = passphrase
        self.keystore_file_path = Path(keystore_file_path)
        self.content = self._get_content()

    def _get_content(self):
        if self.keystore_file_path.exists():
            with self.keystore_file_path.open() as f:
                return json.load(f)

    @property
    def private_key(self):
        if not self.passphrase:
            raise ValueError("Passphrase is not known, can not get private key")

        return decode_keyfile_json(self.content, self.passphrase.encode())

    @property
    def address(self):
        return self.content.get("address")

    @classmethod
    def create(cls, passphrase):
        time_stamp = (
            datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
        )
        uid = uuid.uuid4()

        keystore_file_path = Path(cls.KEYSTORE_FOLDER).joinpath(
            f"UTC--{time_stamp}Z--{uid}"
        )

        keystore_folder_path = Path(keystore_file_path).parent
        keystore_folder_path.mkdir(exist_ok=True)

        with keystore_file_path.open("w") as keyfile:
            private_key = os.urandom(32)
            json.dump(create_keyfile_json(private_key, passphrase.encode()), keyfile)

        return cls(keystore_file_path, passphrase=passphrase)

    @classmethod
    def get_user_accounts(cls):
        pass


class RaidenConfigurationFile:
    pass


class RaidenClient:
    def __init__(self, version=None):
        pass

    def launch(self, configuration_file):
        pass

    @classmethod
    def get_latest_version(cls):
        pass

    @classmethod
    def get_installed_versions(cls):
        pass

    @classmethod
    def install(cls, version=None):
        pass


class EthereumClient:
    pass


class Network:
    MININUM_ETHEREUM_BALANCE_REQUIRED = 0.1
    CONTRACT_TOKEN_NAME = CONTRACT_CUSTOM_TOKEN
    FUNDING_TOKEN_AMOUNT = 0

    @classmethod
    def fund(cls, account):
        raise NotImplementedError

    def mint_token(self, account, token, amount):
        pass


class Goerli(Network):
    FUNDING_TOKEN_AMOUNT = 10 ** 18

    @classmethod
    def fund(cls, account):
        client_hash = hashlib.sha256(uuid.getnode().encode()).hexdigest()

        requests.post(
            "https://faucet.workshop.raiden.network/",
            json={"address": address, "client_hash": client_hash},
        )
