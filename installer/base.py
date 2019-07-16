import os
import sys
import glob
import gzip
import hashlib
import logging
import json
import uuid
import time
import functools
import random
from io import BytesIO
from contextlib import closing
from datetime import datetime
from pathlib import Path
import socket
import string
import subprocess
from typing import Optional
from urllib.parse import urlparse
import tarfile
import zipfile

from raiden_contracts.contract_manager import (
    ContractManager,
    get_contracts_deployment_info,
    contracts_precompiled_path,
)
from raiden_contracts.constants import CONTRACT_CUSTOM_TOKEN, CONTRACT_USER_DEPOSIT
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_utils import to_checksum_address
import requests
import toml
from xdg import XDG_DATA_HOME
from web3 import Web3, HTTPProvider
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

logger = logging.getLogger(__name__)


def make_random_string(length=32):
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


class InstallerError(Exception):
    pass


class FundingError(Exception):
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
    DEFAULT_KEYSTORE_FOLDER = None

    def __init__(self, keystore_file_path: Path, passphrase: Optional[str] = None):
        self.passphrase = passphrase
        self.keystore_file_path = Path(keystore_file_path)
        self.content = self._get_content()
        self._web3_provider = None
        self._web3_ethereum_rpc_endpoint = None

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
        web3_provider = self.get_web3_provider(ethereum_rpc_endpoint)
        return web3_provider.eth.getBalance(to_checksum_address(self.address))

    def get_web3_provider(self, ethereum_rpc_endpoint):
        is_known_rpc_endpoint = (
            self._web3_ethereum_rpc_endpoint == ethereum_rpc_endpoint
        )
        if self._web3_provider is None or not is_known_rpc_endpoint:
            rpc_provider = EthereumRPCProvider.make_from_url(ethereum_rpc_endpoint)
            self._web3_provider = rpc_provider.make_web3_provider(self)
            self._web3_ethereum_rpc_endpoint = ethereum_rpc_endpoint
        return self._web3_provider

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
    def create(cls, passphrase=None):
        if passphrase is None:
            passphrase = make_random_string()

        time_stamp = (
            datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
        )
        uid = uuid.uuid4()

        keystore_file_path = Path(cls.find_keystore_folder_path()).joinpath(
            f"UTC--{time_stamp}Z--{uid}"
        )

        keystore_folder_path = Path(keystore_file_path).parent
        keystore_folder_path.mkdir(parents=True, exist_ok=True)

        with keystore_file_path.open("w") as keyfile:
            private_key = os.urandom(32)
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
        keystore_glob = glob.glob(
            str(cls.find_keystore_folder_path().joinpath("UTC--*"))
        )
        return [cls(keystore_file_path=Path(f)) for f in keystore_glob]


class RaidenClient:
    BINARY_FOLDER_PATH = Path.home().joinpath(".local", "bin")
    RELEASES_URL = "https://api.github.com/repos/raiden-network/raiden/releases"
    DOWNLOADS_URL = "https://github.com/raiden-network/raiden/releases/download"
    BINARY_NAME_FORMAT = "raiden-{release}"
    LATEST_RELEASE = "v0.100.4"
    WEB_UI_INDEX_URL = "http://127.0.0.1:5001"

    def __init__(self, release):
        self.release = release

    def install(self, force=False):

        if self.install_path.exists() and not force:
            raise InstallerError(f"{self.install_path} already exists")

        download_url = self.get_download_url()
        download = requests.get(download_url)
        download.raise_for_status()

        action = (
            self._extract_gzip if download_url.endswith("gz") else self._extract_zip
        )

        action(BytesIO(download.content), self.install_path)
        os.chmod(self.install_path, 0o770)

    def uninstall(self):
        if self.install_path.exists():
            self.install_path.unlink()

    def launch(self, configuration_file):

        uri = urlparse(self.WEB_UI_INDEX_URL)
        subprocess.Popen(
            [str(self.install_path), "--config-file", str(configuration_file.path)]
        )

        while True:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                logger.info("Waiting for raiden to start...")
                time.sleep(1)
                try:
                    connected = sock.connect_ex((uri.netloc, uri.port)) == 0
                    if connected:
                        return
                except socket.gaierror as exc:
                    logger.error(exc)

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
        with zipfile.ZipFile(compressed_data) as zipped:
            with destination_path.open("wb") as binary_file:
                binary_file.write(zipped.read(zipped.filelist[0]))

    def _extract_gzip(self, compressed_data, destination_path):
        with tarfile.open(mode="r:*", fileobj=compressed_data) as tar:
            with destination_path.open("wb") as binary_file:
                binary_file.write(tar.extractfile(tar.getmembers()[0]).read())

    @classmethod
    def get_latest_release(cls):
        try:
            return cls.get_available_releases()[0]
        except Exception:
            return cls(cls.LATEST_RELEASE)

    @classmethod
    @functools.lru_cache()
    def get_available_releases(cls):
        response = requests.get(cls.RELEASES_URL)
        response.raise_for_status()
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
    FAUCET_AVAILABLE = False
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
    def capitalized_name(self):
        return self.name.capitalize()

    def get_contract_address(self, contract_name):
        return get_contracts_deployment_info(self.chain_id)["contracts"][contract_name][
            "address"
        ]

    def fund(self, account):
        raise NotImplementedError(
            "Each network should implement its own method to fund an account"
        )

    @staticmethod
    def get_network_names():
        return list(Network.CHAIN_ID_MAPPING.keys())

    @staticmethod
    def all():
        return [Network.get_by_name(n) for n in Network.get_network_names()]

    @staticmethod
    def get_by_chain_id(chain_id):
        return Network.get_by_name(
            [
                name
                for name, cid in Network.CHAIN_ID_MAPPING.items()
                if cid == chain_id
            ].pop()
        )

    @staticmethod
    def get_by_name(name):
        network_class = {"goerli": Goerli, "ropsten": Ropsten}.get(name, Network)
        return network_class(name)


class Goerli(Network):
    FAUCET_AVAILABLE = True

    def fund(self, account):
        try:
            # client_hash = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()
            client_hash = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
            response = requests.post(
                "https://faucet.workshop.raiden.network/",
                json={"address": account.address, "client_hash": client_hash},
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}")


class Ropsten(Network):
    FAUCET_AVAILABLE = True

    def fund(self, account):
        try:
            response = requests.get(
                f"https://faucet.ropsten.be/donate/{account.address}"
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}")


class EthereumRPCProvider:
    def __init__(self, url):
        self.url = url

    def make_web3_provider(self, account):
        w3 = Web3(HTTPProvider(self.url))
        w3.middleware_stack.add(
            construct_sign_and_send_raw_middleware(account.private_key)
        )
        w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        return w3

    @staticmethod
    def make_from_url(url):
        try:
            return Infura(url)
        except ValueError:
            return EthereumRPCProvider(url)


class Infura(EthereumRPCProvider):
    URL_PATTERN = "https://{network_name}.infura.io/v3/{project_id}"

    def __init__(self, url):
        super().__init__(url)
        if not Infura.is_valid_project_id(self.project_id):
            raise ValueError("{url} is not a valid URL and/or infura project")

        if self.network.name not in Network.get_network_names():
            raise ValueError("{self.network.name} is no valid ethereum network")

    @property
    def network(self):
        network_name = urlparse(self.url).netloc.split(".")[0]
        return Network.get_by_name(network_name.lower())

    @property
    def project_id(self):
        return self.url.split("/")[-1]

    @classmethod
    def make(cls, network: Network, project_id: str):
        return cls(
            cls.URL_PATTERN.format(network_name=network.name, project_id=project_id)
        )

    @staticmethod
    def is_valid_project_id(id_string: str) -> bool:
        try:
            # It should an hex string
            int(id_string, 16)
            return len(id_string) == 32
        except ValueError:
            return False


class Token:
    TOKEN_AMOUNT = 10 ** 18
    USER_DEPOSIT_CONTRACT_NAME = CONTRACT_USER_DEPOSIT
    CUSTOM_TOKEN_CONTRACT_NAME = CONTRACT_CUSTOM_TOKEN

    GAS_REQUIRED_FOR_APPROVE = 70_000
    GAS_REQUIRED_FOR_DEPOSIT = 200_000

    def __init__(self, ethereum_rpc_endpoint, account):
        web3_provider = account.get_web3_provider(ethereum_rpc_endpoint)
        network = Network.get_by_chain_id(int(web3_provider.net.version))
        user_deposit_contract_address = network.get_contract_address(
            self.USER_DEPOSIT_CONTRACT_NAME
        )
        deposit_proxy = self._get_proxy(
            web3_provider,
            self.USER_DEPOSIT_CONTRACT_NAME,
            user_deposit_contract_address,
        )

        token_network_address = deposit_proxy.functions.token().call()
        token_proxy = self._get_proxy(
            web3_provider, self.CUSTOM_TOKEN_CONTRACT_NAME, token_network_address
        )

        self.web3_provider = web3_provider
        self.account = account
        self.deposit_proxy = deposit_proxy
        self.token_proxy = token_proxy
        self.web3_provider.eth.default = self.owner

    @property
    def owner(self):
        return to_checksum_address(self.account.address)

    @property
    def balance(self):
        return self.token_proxy.functions.balanceOf(self.owner).call()

    def _send_raw_transaction(self, contract_function, gas_amount, *args):
        chain_id = int(self.web3_provider.net.version)

        result = contract_function(*args)
        transaction_data = result.buildTransaction(
            {
                "chainId": chain_id,
                "gas": gas_amount,
                "gasPrice": 2 * self.web3_provider.eth.gasPrice,
                "nonce": self.web3_provider.eth.getTransactionCount(self.owner),
            }
        )

        signed = self.web3_provider.eth.account.signTransaction(
            transaction_data, self.account.private_key
        )
        tx_hash = self.web3_provider.eth.sendRawTransaction(signed.rawTransaction)

        return self.web3_provider.eth.waitForTransactionReceipt(tx_hash)

    def _get_proxy(self, web3_provider, contract_name, contract_address):
        contract_manager = ContractManager(contracts_precompiled_path())

        return web3_provider.eth.contract(
            address=contract_address,
            abi=contract_manager.get_contract_abi(contract_name),
        )

    def mint(self, amount: int):
        return self.token_proxy.functions.mint(amount).transact({"from": self.owner})

    def deposit(self, amount: int):
        self._send_raw_transaction(
            self.token_proxy.functions.approve,
            self.GAS_REQUIRED_FOR_APPROVE,
            self.deposit_proxy.address,
            amount,
        )

        return self._send_raw_transaction(
            self.deposit_proxy.functions.deposit,
            self.GAS_REQUIRED_FOR_DEPOSIT,
            self.owner,
            amount,
        )


class RaidenConfigurationFile:
    FOLDER_PATH = XDG_DATA_HOME.joinpath("raiden")

    def __init__(
        self,
        account: Account,
        network: Network,
        ethereum_client_rpc_endpoint: str,
        **kw,
    ):
        self.account = account
        self.network = network
        self.ethereum_client_rpc_endpoint = ethereum_client_rpc_endpoint
        self.accept_disclaimer = kw.get("accept_disclaimer", True)
        self.enable_monitoring = kw.get("enable_monitoring", True)
        self.routing_mode = kw.get("routing_mode", "pfs")
        self.environment_type = kw.get("environment_type", "development")

    def save(self):
        if not self.account.check_passphrase(self.account.passphrase):
            raise ValueError("no valid passphrase for account collected")

        self.FOLDER_PATH.mkdir(parents=True, exist_ok=True)

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
            "keystore-path": str(self.account.__class__.find_keystore_folder_path()),
            "keystore-file-path": str(self.account.keystore_file_path),
            "address": to_checksum_address(self.account.address),
            "password-file": str(self.passphrase_file_path),
            "user-deposit-contract-address": self.network.get_contract_address(
                CONTRACT_USER_DEPOSIT
            ),
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
        has_token_deposit = self.account
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
    def get_available_configurations(cls):
        config_glob = str(cls.FOLDER_PATH.joinpath("config-*.toml"))

        configurations = []
        for config_file_path in glob.glob(config_glob):
            try:
                configurations.append(cls.load(Path(config_file_path)))
            except (ValueError, KeyError) as exc:
                logger.warn(
                    f"Failed to load {config_file_path} as configuration file: {exc}"
                )

        return configurations

    @classmethod
    def load(cls, file_path: Path):
        file_name, _ = os.path.splitext(os.path.basename(file_path))

        _, address, network_name = file_name.split("-")

        with file_path.open() as config_file:
            data = toml.load(config_file)
            passphrase = PassphraseFile(Path(data["password-file"])).retrieve()
            account = Account(data["keystore-file-path"], passphrase=passphrase)
            return cls(
                account=account,
                ethereum_client_rpc_endpoint=data["eth-rpc-endpoint"],
                network=Network.get_by_name(network_name),
            )

    @classmethod
    def get_by_filename(cls, file_name):
        return cls.load(cls.FOLDER_PATH.joinpath(file_name))

    @classmethod
    def get_launchable_configurations(cls):
        return [cfg for cfg in cls.get_available_configurations() if cfg.is_launchable]

    @classmethod
    def get_ethereum_rpc_endpoints(cls):
        endpoints = []

        config_glob = glob.glob(cls.FOLDER_PATH.joinpath("*.toml"))
        for config_file_path in config_glob:
            with open(config_file_path) as config_file:
                data = toml.load(config_file)
                endpoints.append(
                    EthereumRPCProvider.make_from_url(data["eth-rpc-endpoint"])
                )
        return endpoints
