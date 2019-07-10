import os
import sys
import glob
import gzip
import hashlib
import json
import uuid
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Optional
import zipfile

import requests
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from raiden_contracts.constants import CONTRACT_CUSTOM_TOKEN, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import get_contracts_deployment_info
from xdg import XDG_DATA_HOME


class InstallerError(Exception):
    pass


class PassphraseFile:
    # FIXME: Right now we are writing/reading to a plain text file, which
    # may be a security risk and put the user's funds at risk.

    def __init__(self, file_path):
        self.file_path = file_path

    def store(self, passphrase):
        with self.file_path.open("w") as f:
            f.write(passphrase)

    def retrieve(self):
        with self.file_path.open() as f:
            return f.read()


class Account:
    KEYSTORE_FOLDER_PATH = XDG_DATA_HOME

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

        keystore_file_path = Path(cls.KEYSTORE_FOLDER_PATH).joinpath(
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
    CONFIG_FOLDER_PATH = XDG_DATA_HOME.joinpath("raiden")

    def __init__(self, account, ethereum_client, network, **kw):
        self.account = account
        self.ethereum_client = ethereum_client
        self.network = network
        self.accept_disclaimer = kw.get("accept_disclaimer", True)
        self.enable_monitoring = kw.get("enable_monitoring", True)
        self.routing_mode = kw.get("routing_mode", "pfs")
        self.environment_type = kw.get("environment_type", "development")

        self.user_deposit_address = self.network.get_user_deposit_address()

    def save(self):
        self.CONFIG_FOLDER_PATH.mkdir(exist_ok=True)

        with open(self.path, "w") as config_file:
            toml.dump(self.configuration_data, config_file)

    @property
    def path_finding_service_url(self):
        return f"https://pfs-{self.network.NAME}.services-dev.raiden.network"

    @property
    def configuration_data(self):
        return {
            "environment-type": self.environment_type,
            "keystore-path": str(self.account.keystore_file_path),
            "address": to_checksum_address(self.account.address),
            "password-file": str(self.passphrase_file_path),
            "user-deposit-contract-address": self.user_deposit_address,
            "network-id": self.network.NAME,
            "accept-disclaimer": self.accept_disclaimer,
            "eth-rpc-endpoint": self.ethereum_client.rpc_endpoint,
            "routing-mode": self.routing_mode,
            "pathfinding-service-address": self.path_finding_service_url,
            "enable-monitoring": self.enable_monitoring,
        }

    @property
    def file_name(self):
        return "config-{self.account.address}-{self.network.NAME}-{self.ethereum_client.name}.toml"

    @property
    def path(self):
        return self.CONFIG_FOLDER_PATH.joinpath(self.file_name)

    @property
    def passphrase_file_path(self):
        return self.CONFIG_FOLDER_PATH.joinpath(
            f"{self.account.address}.passphrase.txt"
        )

    @classmethod
    def get_available_configurations(cls):
        config_glob = str(cls.CONFIG_FOLDER_PATH.joinpath("config-*.toml"))

        configurations = []
        for config_file_path in glob.glob(config_glob):
            file_name, _ = os.path.splitext(os.path.basename(config_file_path))

            _, address, network_name, ethereum_client_name = file_name.split("-")

            with Path(config_file_path).open() as config_file:
                data = toml.load(config_file)
                passphrase = Passphrase(data["password-file"]).retrieve()

                configurations.append(
                    cls(
                        account=Account(data["keystore-path"], passphrase=passphrase),
                        ethereum_client=EthereumClient.get_by_name(ethreum_client_name),
                        network=Network.get_by_name(network_by_name),
                    )
                )
        return configurations


class RaidenClient:
    BINARY_FOLDER_PATH = Path.home().joinpath(".local", "bin")
    RELEASES_URL = "https://api.github.com/repos/raiden-network/raiden/releases"
    DOWNLOADS_URL = "https://github.com/raiden-network/raiden/releases/download"
    BINARY_NAME_FORMAT = "raiden-{release}"

    def __init__(self, release):
        self.release = release

    def install(self, force=False):

        if self.install_path.exists() and not force:
            raise InstallerError(f"{self.install_path} already exists")

        download_url = self.get_download_url()
        download = requests.get(download_url)

        action = (
            self._extract_gzip if download_url.endswith("gz") else self._extract_zip
        )
        action(BytesIO(download.content))

    def launch(self, configuration_file):
        pass

    def get_download_url(self, system=None):
        system_platform = system or sys.platform

        extension = "tar.gz" if system_platform == "linux" else "zip"
        label = {"darwin": "macOS", "linux": "linux"}[system_platform]

        filename = f"raiden-{self.release}-{label}-x86_64.{extension}"
        return f"{self.DOWNLOADS_URL}/{self.release}/{filename}"

    @property
    def binary_name(self):
        return self.BINARY_NAME_FORMAT.format(release=self.release)

    @property
    def install_path(self):
        return Path(self.BINARY_FOLDER_PATH).joinpath(self.binary_name)

    def _extract_zip(self, compressed_data):
        zipped = zipfile.ZipFile(compressed_data)
        zipped.extract(zipped.filelist[0], path=self.install_path)

    def _extract_gzip(self, compressed_data):
        with gzip.open(compressed_data) as compressed_file:
            with self.install_path.open("wb") as binary_file:
                binary_file.write(compressed_file.read())

    @classmethod
    def get_latest_release(cls):
        response = requests.get(cls.RELEASES_URL)
        return cls(response.json()[0].get("tag_name"))

    @classmethod
    def get_installed_releases(cls):
        all_raiden_glob = cls.BINARY_FOLDER_PATH.format(release="*")
        installed_raidens = [
            os.path.basename(raiden_path)
            for raiden_path in glob.glob(
                str(cls.BINARY_FOLDER_PATH.joinpath(all_raiden_glob))
            )
        ]

        installed_releases = [raiden.split("-")[-1] for raiden in installed_raidens]

        return [cls(release) for release in installed_releases]


class EthereumClient:
    @staticmethod
    def get_by_name(name):
        return {"geth": Geth, "parity": Parity, "infura": Infura}[name]

    @classmethod
    def get_data_folder_path(cls) -> Path:
        home = Path.home()

        if sys.platform == "darwin":
            folder_path = home.joinpath("Library", "Ethereum")
        elif sys.platform in ("win32", "cygwin"):
            folder_path = home.joinpath("AppData", "Roaming", "Ethereum")
        elif os.name == "posix":
            folder_path = home.joinpath(".ethereum")
        else:
            raise RuntimeError("Unsupported Operating System")

        if not folder_path.is_dir():
            raise ValueError("{folder_path} is not a directory")
        return folder_path


class Geth(EthereumClient):
    pass


class Parity(EthereumClient):
    pass


class Infura(EthereumClient):
    pass


class Network:
    MININUM_ETHEREUM_BALANCE_REQUIRED = 0.1
    CONTRACT_TOKEN_NAME = CONTRACT_CUSTOM_TOKEN
    FUNDING_TOKEN_AMOUNT = 0
    NAME = None

    @classmethod
    def fund(cls, account):
        raise NotImplementedError

    @classmethod
    def mint_token(self, account, token, amount):
        pass

    @classmethod
    def get_user_deposit_address(cls):
        contracts = get_contracts_deployment_info(cls.CHAIN_ID)["contracts"]
        return contracts[CONTRACT_USER_DEPOSIT]["address"]


class Goerli(Network):
    FUNDING_TOKEN_AMOUNT = 10 ** 18
    NAME = "goerli"

    @classmethod
    def fund(cls, account):
        client_hash = hashlib.sha256(uuid.getnode().encode()).hexdigest()

        requests.post(
            "https://faucet.workshop.raiden.network/",
            json={"address": account.address, "client_hash": client_hash},
        )
