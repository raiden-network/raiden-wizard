import os
import sys
import glob
import gzip
import hashlib
import logging
import json
import uuid
import functools
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Optional
import zipfile

from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_utils import to_checksum_address
from raiden_contracts.constants import CONTRACT_CUSTOM_TOKEN, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import get_contracts_deployment_info
import requests
import toml
from xdg import XDG_DATA_HOME
from web3 import Web3, HTTPProvider

logger = logging.getLogger(__name__)


class InstallerError(Exception):
    pass


class PassphraseFile:
    # FIXME: Right now we are writing/reading to a plain text file, which
    # may be a security risk and put the user's funds at risk.

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def store(self, passphrase):
        with self.file_path.open("w") as f:
            f.write(passphrase)

    def retrieve(self):
        with self.file_path.open() as f:
            return f.read()


class Account:
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

    def get_balance(self, ethereum_rpc_endpoint):
        w3 = Web3(HTTPProvider(ethereum_rpc_endpoint))
        return w3.eth.getBalance(to_checksum_address(self.address))

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
    def create(cls, passphrase):
        time_stamp = (
            datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
        )
        uid = uuid.uuid4()

        keystore_file_path = Path(cls.find_keystore_folder_path()).joinpath(
            f"UTC--{time_stamp}Z--{uid}"
        )

        keystore_folder_path = Path(keystore_file_path).parent
        keystore_folder_path.mkdir(exist_ok=True)

        with keystore_file_path.open("w") as keyfile:
            private_key = os.urandom(32)
            json.dump(create_keyfile_json(private_key, passphrase.encode()), keyfile)

        return cls(keystore_file_path, passphrase=passphrase)

    @classmethod
    def find_keystore_folder_path(cls):
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
        keystore_glob = glob.glob(
            str(cls.find_keystore_folder_path().joinpath("UTC--*"))
        )
        return [cls(keystore_file_path=Path(f)) for f in keystore_glob]


class RaidenConfigurationFile:
    FOLDER_PATH = XDG_DATA_HOME.joinpath("raiden")

    def __init__(self, account, network, ethereum_client_rpc_endpoint, **kw):
        self.account = account
        self.network = network
        self.ethereum_client_rpc_endpoint = ethereum_client_rpc_endpoint
        self.accept_disclaimer = kw.get("accept_disclaimer", True)
        self.enable_monitoring = kw.get("enable_monitoring", True)
        self.routing_mode = kw.get("routing_mode", "pfs")
        self.environment_type = kw.get("environment_type", "development")

        self.user_deposit_address = self.network.user_deposit_address

    def save(self):
        if not self.account.check_passphrase(self.account.passphrase):
            raise ValueError("no valid passphrase for account collected")

        self.FOLDER_PATH.mkdir(exist_ok=True)

        passphrase_file = PassphraseFile(self.passphrase_file_path)
        passphrase_file.store(self.account.passphrase)

        with open(self.path, "w") as config_file:
            toml.dump(self.configuration_data, config_file)

    @property
    def path_finding_service_url(self):
        return f"https://pfs-{self.network.name}.services-dev.raiden.network"

    @property
    def configuration_data(self):
        return {
            "environment-type": self.environment_type,
            "keystore-path": str(self.account.keystore_file_path),
            "address": to_checksum_address(self.account.address),
            "password-file": str(self.passphrase_file_path),
            "user-deposit-contract-address": self.user_deposit_address,
            "network-id": self.network.name,
            "accept-disclaimer": self.accept_disclaimer,
            "eth-rpc-endpoint": self.ethereum_client_rpc_endpoint,
            "routing-mode": self.routing_mode,
            "pathfinding-service-address": self.path_finding_service_url,
            "enable-monitoring": self.enable_monitoring,
        }

    @property
    def file_name(self):
        return f"config-{self.account.address}-{self.network.name}.toml"

    @property
    def path(self):
        return self.FOLDER_PATH.joinpath(self.file_name)

    @property
    def passphrase_file_path(self):
        return self.FOLDER_PATH.joinpath(f"{self.account.address}.passphrase.txt")

    @property
    def balance(self):
        return self.account.get_balance(self.ethereum_client_rpc_endpoint)

    @property
    def is_launchable(self):
        return self.balance >= self.network.MINIMUM_ETHEREUM_BALANCE_REQUIRED

    @property
    def short_description(self):
        account_description = (
            f"Account {self.account.address} (Balance: {self.balance})"
        )
        network_description = (
            f"{self.network.name} via {self.ethereum_client_rpc_endpoint}"
        )
        return " - ".join((str(self.path), account_description, network_description))

    @classmethod
    def get_launchable_configurations(cls):
        return [cfg for cfg in cls.get_available_configurations() if cfg.is_launchable]

    @classmethod
    def get_available_configurations(cls):
        config_glob = str(cls.FOLDER_PATH.joinpath("config-*.toml"))

        configurations = []
        for config_file_path in glob.glob(config_glob):
            try:
                file_name, _ = os.path.splitext(os.path.basename(config_file_path))

                _, address, network_name = file_name.split("-")

                with Path(config_file_path).open() as config_file:
                    data = toml.load(config_file)
                    passphrase = PassphraseFile(Path(data["password-file"])).retrieve()

                    configurations.append(
                        cls(
                            account=Account(
                                data["keystore-path"], passphrase=passphrase
                            ),
                            ethereum_client_rpc_endpoint=data["eth-rpc-endpoint"],
                            network=Network.get_by_name(network_name),
                        )
                    )
            except (ValueError, KeyError) as exc:
                logger.warn(
                    f"Failed to load {config_file_path} as configuration file: {exc}"
                )

        return configurations


class RaidenClient:
    BINARY_FOLDER_PATH = Path.home().joinpath(".local", "bin")
    RELEASES_URL = "https://api.github.com/repos/raiden-network/raiden/releases"
    DOWNLOADS_URL = "https://github.com/raiden-network/raiden/releases/download"
    BINARY_NAME_FORMAT = "raiden-{release}"
    LATEST_RELEASE = "v0.100.4"

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
        action(BytesIO(download.content), self.install_path)
        os.chmod(self.install_path, 0o770)

    def uninstall(self):
        if self.install_path.exists():
            self.install_path.unlink()

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
    def is_installed(self):
        return self.install_path.exists()

    @property
    def install_path(self):
        return Path(self.BINARY_FOLDER_PATH).joinpath(self.binary_name)

    def _extract_zip(self, compressed_data, destination_path):
        zipped = zipfile.ZipFile(compressed_data)
        zipped.extract(zipped.filelist[0], path=destination_path)

    def _extract_gzip(self, compressed_data, destination_path):
        with gzip.open(compressed_data) as compressed_file:
            with destination_path.open("wb") as binary_file:
                binary_file.write(compressed_file.read())

    @classmethod
    def get_latest_release(cls):
        return cls.get_available_releases()[0]

    @classmethod
    @functools.lru_cache()
    def get_available_releases(cls):
        response = requests.get(cls.RELEASES_URL)
        return [cls(release.get("tag_name")) for release in response.json()]

    @classmethod
    def get_installed_releases(cls):
        all_raiden_glob = cls.BINARY_NAME_FORMAT.format(release="*")
        installed_raidens = [
            os.path.basename(raiden_path)
            for raiden_path in glob.glob(
                str(cls.BINARY_FOLDER_PATH.joinpath(all_raiden_glob))
            )
        ]

        installed_releases = [raiden.split("-", 1)[-1] for raiden in installed_raidens]

        return [cls(release) for release in installed_releases]


class Network:
    MINIMUM_ETHEREUM_BALANCE_REQUIRED = 0.01
    CONTRACT_TOKEN_NAME = CONTRACT_CUSTOM_TOKEN
    FUNDING_TOKEN_AMOUNT = 0
    CHAIN_ID_MAPPING = {
        "mainnet": 1,
        "ropsten": 3,
        "rinkeby": 4,
        "goerli": 5,
        "kovan": 42,
    }

    def __init__(self, name):
        self.name = name
        self.chain_id = self.CHAIN_ID_MAPPING[name.lower()]

    @property
    def user_deposit_address(self):
        contracts = get_contracts_deployment_info(self.chain_id)["contracts"]
        return contracts[CONTRACT_USER_DEPOSIT]["address"]

    @staticmethod
    def get_network_names():
        return list(Network.CHAIN_ID_MAPPING.keys())

    @staticmethod
    def get_by_name(name):
        network_class = {"goerli": Goerli}.get(name, Network)
        return network_class(name)


class Goerli(Network):
    FUNDING_TOKEN_AMOUNT = 10 ** 18

    @staticmethod
    def fund(account):
        client_hash = hashlib.sha256(uuid.getnode().encode()).hexdigest()

        requests.post(
            "https://faucet.workshop.raiden.network/",
            json={"address": account.address, "client_hash": client_hash},
        )


def build_infura_url(network: Network, project_id: str) -> str:
    return f"https://{network.name}.infura.io/v3/{project_id}"


def is_valid_infura_project_id(id_string: str) -> bool:
    try:
        # It should an hex string
        int(id_string, 16)
        return len(id_string) == 32
    except ValueError:
        return False
