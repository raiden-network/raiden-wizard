import datetime
import functools
import glob
import hashlib
import json
import logging
import os
import random
import re
import socket
import string
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile
import json
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

import psutil
import requests
import toml
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_utils import to_checksum_address
from raiden_contracts.constants import CONTRACT_CUSTOM_TOKEN, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import (
    ContractManager,
    contracts_precompiled_path,
    get_contracts_deployment_info,
)
from web3 import HTTPProvider, Web3
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

from xdg import XDG_DATA_HOME

logger = logging.getLogger(__name__)


def make_random_string(length=32):
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


class InstallerError(Exception):
    pass


class FundingError(Exception):
    pass


class RaidenClientError(Exception):
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
        return None

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
        is_known_rpc_endpoint = self._web3_ethereum_rpc_endpoint == ethereum_rpc_endpoint
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
            datetime.datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
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
        keystore_glob = glob.glob(str(cls.find_keystore_folder_path().joinpath("UTC--*")))
        return [cls(keystore_file_path=Path(f)) for f in keystore_glob]


class RaidenClient:
    BINARY_FOLDER_PATH = Path.home().joinpath(".local", "bin")
    BINARY_NAME_FORMAT = "raiden-{release}"
    WEB_UI_INDEX_URL = "http://127.0.0.1:5001"

    RELEASE_INDEX_URL = "https://api.github.com/repos/raiden-network/raiden/releases"
    DOWNLOAD_INDEX_URL = "https://github.com/raiden-network/raiden/releases/download"
    FILE_NAME_SUFFIX = "macOS-x86_64.zip" if sys.platform == "darwin" else "linux-x86_64.tar.gz"

    def __init__(self, release, **kw):
        self.release = release
        self._process_id = self.get_process_id()

        for attr, value in kw.items():
            setattr(self, attr, value)

    def __eq__(self, other):
        return all(
            [self.major == other.major, self.minor == other.minor, self.revision == other.revision]
        )

    def __lt__(self, other):
        if self.major != other.major:
            return self.major < other.major

        if self.minor != other.minor:
            return self.minor < other.minor

        return self.revision < other.revision

    def __gt__(self, other):
        if self.major != other.major:
            return self.major > other.major

        if self.minor != other.minor:
            return self.minor > other.minor

        return self.revision > other.revision

    def __cmp__(self, other):
        if self.__gt__(other):
            return 1
        elif self.__lt__(other):
            return -1
        else:
            return 0

    @property
    def release_date(self):
        return datetime.date(year=int(self.year), month=int(self.month), day=int(self.day))

    @property
    def version(self):
        return f"{self.major}.{self.minor}.{self.revision}"

    def install(self, force=False):

        if self.install_path.exists() and not force:
            raise InstallerError(f"{self.install_path} already exists")

        self.BINARY_FOLDER_PATH.mkdir(parents=True, exist_ok=True)

        download = requests.get(self.download_url)
        download.raise_for_status()

        action = self._extract_gzip if self.download_url.endswith("gz") else self._extract_zip

        action(BytesIO(download.content), self.install_path)
        os.chmod(self.install_path, 0o770)

    def uninstall(self):
        if self.install_path.exists():
            self.install_path.unlink()

    def launch(self, configuration_file):
        proc = subprocess.Popen(
            [str(self.install_path), "--config-file", str(configuration_file.path)]
        )
        self._process_id = proc.pid

    def wait_for_web_ui_ready(self):
        if not self.is_running:
            raise RuntimeError("Raiden is not running")

        uri = urlparse(self.WEB_UI_INDEX_URL)

        while True:
            self._process_id = self.get_process_id()
            if not self.is_running:
                raise RaidenClientError("client process terminated while waiting for web ui")

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                logger.info("Waiting for raiden to start...")
                try:
                    connected = sock.connect_ex((uri.hostname, uri.port)) == 0
                    if connected:
                        return
                except socket.gaierror:
                    pass
                time.sleep(1)

    def get_process_id(self):
        def is_running_raiden(process):
            try:
                is_raiden = self.binary_name.lower() == process.name().lower()
                is_dead = process.status() is [psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE]

                return is_raiden and not is_dead
            except psutil.ZombieProcess:
                return False

        processes = [p for p in psutil.process_iter() if is_running_raiden(p)]

        try:
            return max(p.pid for p in processes)
        except ValueError:
            return None

    @property
    def binary_name(self):
        return self.BINARY_NAME_FORMAT.format(release=self.release)

    @property
    def is_installed(self):
        return self.install_path.exists()

    @property
    def is_running(self):
        return self.get_process_id() is not None

    @property
    def install_path(self):
        return Path(self.BINARY_FOLDER_PATH).joinpath(self.binary_name)

    @property
    def download_url(self):
        return self.browser_download_url

    def _extract_zip(self, compressed_data, destination_path):
        with zipfile.ZipFile(compressed_data) as zipped:
            with destination_path.open("wb") as binary_file:
                binary_file.write(zipped.read(zipped.filelist[0]))

    def _extract_gzip(self, compressed_data, destination_path):
        with tarfile.open(mode="r:*", fileobj=compressed_data) as tar:
            with destination_path.open("wb") as binary_file:
                binary_file.write(tar.extractfile(tar.getmembers()[0]).read())

    @classmethod
    def get_file_pattern(cls):
        return fr"{cls.FILE_NAME_PATTERN}-{cls.FILE_NAME_SUFFIX}"

    @classmethod
    def get_latest_release(cls):
        return max(cls.get_available_releases())

    @classmethod
    @functools.lru_cache()
    def get_available_releases(cls):
        response = requests.get(cls.RELEASE_INDEX_URL)
        response.raise_for_status()
        return sorted(cls._make_releases(response), reverse=True)

    @classmethod
    def get_installed_releases(cls):
        return [release for release in cls.get_available_releases() if release.is_installed]

    @classmethod
    def _make_releases(cls, index_response):
        def get_date(timestamp):
            return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").date()

        releases = []
        for release_data in index_response.json():
            for asset_data in release_data.get("assets", []):
                regex = re.match(cls.get_file_pattern(), asset_data["name"])
                if regex:
                    release_date = get_date(release_data["published_at"])
                    major, minor, revision = regex["major"], regex["minor"], regex["revision"]
                    releases.append(
                        cls(
                            release=f"{major}.{minor}.{revision}",
                            year=release_date.year,
                            month=release_date.month,
                            day=release_date.day,
                            major=major,
                            minor=minor,
                            revision=revision,
                            browser_download_url=asset_data.get("browser_download_url"),
                        )
                    )
        return releases


class RaidenRelease(RaidenClient):
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)"

    @property
    def version(self):
        return f"Raiden {self.major}.{self.minor}.{self.revision}"


class RaidenTestnetRelease(RaidenClient):
    BINARY_NAME_FORMAT = "raiden-unstable-{release}"
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+).(?P<extra>.+)"

    @property
    def version(self):
        return f"Raiden Preview {self.major}.{self.minor}.{self.revision} (Testnet only)"


class RaidenNightly(RaidenClient):
    BINARY_NAME_FORMAT = "raiden-nightly-{release}"
    RELEASE_INDEX_URL = "https://raiden-nightlies.ams3.digitaloceanspaces.com"
    FILE_NAME_PATTERN = (
        r"raiden-nightly-(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)"
        r"T(?P<hour>\d+)-(?P<minute>\d+)-(?P<second>\d+)-"
        r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)\.(?P<extra>.+)"
    )

    @property
    def version(self):
        return f"Raiden Nightly Build {self.major}.{self.minor}.{self.revision}-{self.release}"

    @property
    def download_url(self):
        return (
            f"{self.RELEASE_INDEX_URL}/"
            f"raiden-nightly-"
            f"{self.year:04}-{self.month:02}-{self.day:02}"
            f"T{self.hour}-{self.minute}-{self.second}-"
            f"v{self.major}.{self.minor}.{self.revision}.{self.extra}-"
            f"{self.FILE_NAME_SUFFIX}"
        )

    def __eq__(self, other):
        return self.release == other.release and self.release_date == other.release_date

    def __lt__(self, other):
        return self.release_date < other.release_date

    def __gt__(self, other):
        return self.release_date > other.release_date

    def __cmp__(self, other):
        if self.release_date > other.release_date:
            return 1
        elif self.release_date < other.release_date:
            return -1
        else:
            return 0

    @classmethod
    def _make_releases(cls, index_response):
        xmlns = "http://s3.amazonaws.com/doc/2006-03-01/"

        def get_children_by_tag(node, tag):
            return node.findall(f"{{{xmlns}}}{tag}", namespaces={"xmlns": xmlns})

        tree = ElementTree.fromstring(index_response.content)

        content_nodes = get_children_by_tag(tree, "Contents")
        all_keys = [get_children_by_tag(node, "Key")[0].text for node in content_nodes]

        nightlies = {
            k: v.groupdict()
            for k, v in {key: re.match(cls.get_file_pattern(), key) for key in all_keys}.items()
            if v
        }

        release_name_template = "{year:0>4}{month:0>2}{day:0>2}"
        for key, value in nightlies.items():
            nightlies[key]["release"] = release_name_template.format(**value)
            nightlies[key]["year"] = int(nightlies[key]["year"])
            nightlies[key]["month"] = int(nightlies[key]["month"])
            nightlies[key]["day"] = int(nightlies[key]["day"])

        return [cls(**nightly) for nightly in nightlies.values()]


class Network:
    MINIMUM_ETHEREUM_BALANCE_REQUIRED = 0.01
    FAUCET_AVAILABLE = False
    CHAIN_ID_MAPPING = {"mainnet": 1, "ropsten": 3, "rinkeby": 4, "goerli": 5, "kovan": 42}

    def __init__(self, name):
        self.name = name
        self.chain_id = self.CHAIN_ID_MAPPING[name.lower()]

    @property
    def capitalized_name(self):
        return self.name.capitalize()

    def get_contract_address(self, contract_name):
        return get_contracts_deployment_info(self.chain_id)["contracts"][contract_name]["address"]

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
            [name for name, cid in Network.CHAIN_ID_MAPPING.items() if cid == chain_id].pop()
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
    def fund(self, account):
        try:
            response = requests.get(f"https://faucet.ropsten.be/donate/{account.address}")
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}")


class EthereumRPCProvider:
    def __init__(self, url):
        self.url = url

    def make_web3_provider(self, account):
        w3 = Web3(HTTPProvider(self.url))
        w3.middleware_stack.add(construct_sign_and_send_raw_middleware(account.private_key))
        w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        return w3

    @staticmethod
    def make_from_url(url):
        try:
            return Infura(url)
        except ValueError:
            return EthereumRPCProvider(url)


class Infura(EthereumRPCProvider):
    URL_PATTERN = "https://{network_name}.infura.io:443/v3/{project_id}"

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

    @property
    def endpoint(self):
        return self.url[8:]

    @classmethod
    def make(cls, network: Network, project_id: str):
        return cls(cls.URL_PATTERN.format(network_name=network.name, project_id=project_id))

    @staticmethod
    def is_valid_project_id(id_string: str) -> bool:
        try:
            # It should an hex string
            int(id_string, 16)
            return len(id_string) == 32
        except ValueError:
            return False


class Token:
    TOKEN_AMOUNT = 10 ** 21
    USER_DEPOSIT_CONTRACT_NAME = CONTRACT_USER_DEPOSIT
    CUSTOM_TOKEN_CONTRACT_NAME = CONTRACT_CUSTOM_TOKEN

    GAS_REQUIRED_FOR_MINT = 100_000
    GAS_REQUIRED_FOR_APPROVE = 70_000
    GAS_REQUIRED_FOR_DEPOSIT = 200_000

    def __init__(self, ethereum_rpc_endpoint, account):
        web3_provider = account.get_web3_provider(ethereum_rpc_endpoint)
        network = Network.get_by_chain_id(int(web3_provider.net.version))
        user_deposit_contract_address = network.get_contract_address(
            self.USER_DEPOSIT_CONTRACT_NAME
        )
        deposit_proxy = self._get_proxy(
            web3_provider, self.USER_DEPOSIT_CONTRACT_NAME, user_deposit_contract_address
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
            address=contract_address, abi=contract_manager.get_contract_abi(contract_name)
        )

    def mint(self, amount: int):
        return self._send_raw_transaction(
            self.token_proxy.functions.mint, self.GAS_REQUIRED_FOR_MINT, amount
        )

    def deposit(self, amount: int):
        self._send_raw_transaction(
            self.token_proxy.functions.approve,
            self.GAS_REQUIRED_FOR_APPROVE,
            self.deposit_proxy.address,
            amount,
        )

        return self._send_raw_transaction(
            self.deposit_proxy.functions.deposit, self.GAS_REQUIRED_FOR_DEPOSIT, self.owner, amount
        )

class BaseConfigurationFile:
    FOLDER_PATH = XDG_DATA_HOME.joinpath("raiden")

    @property
    def path(self):
        return self.FOLDER_PATH.joinpath(self.file_name)

    @classmethod
    def get_by_filename(cls, file_name):
        return cls.load(cls.FOLDER_PATH.joinpath(file_name))


class RaidenConfigurationFile:
    def __init__(
        self, account: Account, network: Network, ethereum_client_rpc_endpoint: str, **kw
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
        return f"https://pfs-{self.network.name}-with-fee.services-dev.raiden.network"

    @property
    def configuration_data(self):
        base_config = {
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
            "enable-monitoring": self.enable_monitoring,
        }

        if self.routing_mode == "pfs":
            base_config.update({"pathfinding-service-address": self.path_finding_service_url})

        return base_config

    @property
    def file_name(self):
        return f"config-{self.account.address}-{self.network.name}.toml"

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
        account_description = f"Account {self.account.address} (Balance: {self.balance})"
        network_description = f"{self.network.name} via {self.ethereum_client_rpc_endpoint}"
        return " - ".join((str(self.path), account_description, network_description))

    @classmethod
    def get_available_configurations(cls):
        config_glob = str(cls.FOLDER_PATH.joinpath("config-*.toml"))

        configurations = []
        for config_file_path in glob.glob(config_glob):
            try:
                configurations.append(cls.load(Path(config_file_path)))
            except (ValueError, KeyError) as exc:
                logger.warn(f"Failed to load {config_file_path} as configuration file: {exc}")

        return configurations

    @classmethod
    def load(cls, file_path: Path):
        file_name, _ = os.path.splitext(os.path.basename(file_path))

        _, _, network_name = file_name.split("-")

        with file_path.open() as config_file:
            data = toml.load(config_file)
            passphrase = PassphraseFile(Path(data["password-file"])).retrieve()
            account = Account(data["keystore-file-path"], passphrase=passphrase)
            return cls(
                account=account,
                ethereum_client_rpc_endpoint=data["eth-rpc-endpoint"],
                network=Network.get_by_name(network_name),
                routing_mode=data["routing-mode"],
                enable_monitoring=data["enable-monitoring"],
            )

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
                endpoints.append(EthereumRPCProvider.make_from_url(data["eth-rpc-endpoint"]))
        return endpoints


class RaidenDappConfigurationFile:
    def __init__(self, private_key: str, infura_endpoint: Infura):        
        self.private_key = private_key
        self.infura_endpoint = infura_endpoint
        
    def save(self):
        self.FOLDER_PATH.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as config_file:
            json.dumps(self.configuration_data, config_file)

    @property
    def configuration_data(self):
        return {
            "INFURA_ENDPOINT": self.infura_endpoint.endpoint,
            "PRIVATE_KEY": self.private_key
        }

    @property
    def file_name(self):
        keyfile = create_keyfile_json(self.private_key)
        return f"config-{keyfile["address"]}-{self.infura_endpoint.network}_dapp.json"

    @classmethod
    def load(cls, file_path: Path):
        file_name, _ = os.path.splitext(os.path.basename(file_path))

        _, _, network_name = file_name.split("-")

        with file_path.open() as config_file:
            data = json.loads(config_file)
            return cls(
                private_key=data["PRIVATE_KEY"],
                infura_endpoint=data["INFURA_ENDPOINT"]
            )

