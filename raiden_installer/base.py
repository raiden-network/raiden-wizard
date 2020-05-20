import glob
import os
from pathlib import Path
from typing import List

import toml
from eth_utils import to_checksum_address
from xdg import XDG_DATA_HOME

from raiden_installer import log, network_settings
from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import EthereumRPCProvider, make_web3_provider
from raiden_installer.network import Network


class PassphraseFile:
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def store(self, passphrase):
        directory_path = self.file_path.parent.absolute()
        directory_path.mkdir(parents=True, exist_ok=True)

        with self.file_path.open("w") as f:
            f.write(passphrase)

    def retrieve(self):
        with self.file_path.open() as f:
            return f.read()


class RaidenConfigurationFile:
    FOLDER_PATH = XDG_DATA_HOME.joinpath("raiden")

    def __init__(
        self, account_filename: str, network: Network, ethereum_client_rpc_endpoint: str, **kw
    ):
        if 'passphrase' in kw:
            self.account = Account(account_filename, passphrase=kw.get('passphrase'))
        else:
            self.account = Account(account_filename)
        self.account_filename = account_filename
        self.network = network
        self.settings = network_settings[network.name]
        self.ethereum_client_rpc_endpoint = ethereum_client_rpc_endpoint
        self.accept_disclaimer = kw.get("accept_disclaimer", True)
        self.enable_monitoring = kw.get("enable_monitoring", self.settings.monitoring_enabled)
        self.routing_mode = kw.get("routing_mode", self.settings.routing_mode)
        self.services_version = self.settings.services_version
        self._initial_funding_txhash = kw.get("_initial_funding_txhash")

    @property
    def path_finding_service_url(self):
        return f"https://pfs-{self.network.name}.services-{self.services_version}.raiden.network"

    @property
    def configuration_data(self):
        base_config = {
            "environment-type": self.environment_type,
            "keystore-path": str(self.account.__class__.find_keystore_folder_path()),
            "address": to_checksum_address(self.account.address),
            "network-id": self.network.name,
            "accept-disclaimer": self.accept_disclaimer,
            "eth-rpc-endpoint": self.ethereum_client_rpc_endpoint,
            "routing-mode": self.routing_mode,
            "enable-monitoring": self.enable_monitoring,
            "_initial_funding_txhash": self._initial_funding_txhash,
        }

        # If the config is for a demo-env we'll need to add/overwrite some settings
        if self.settings.client_release_channel == "demo_env":  # noqa
            base_config.update({"matrix-server": self.settings.matrix_server})  # noqa
            base_config["routing-mode"] = "pfs"
            base_config[
                "pathfinding-service-address"
            ] = self.settings.pathfinding_service_address  # noqa

        return base_config

    @property
    def environment_type(self):
        return "production" if self.network.name == "mainnet" else "development"

    @property
    def file_name(self):
        return f"config-{self.account.address}-{self.network.name}.toml"

    @property
    def path(self):
        return self.FOLDER_PATH.joinpath(self.file_name)

    @property
    def ethereum_balance(self):
        w3 = make_web3_provider(self.ethereum_client_rpc_endpoint, self.account)
        return self.account.get_ethereum_balance(w3)

    def save(self):
        self.FOLDER_PATH.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as config_file:
            toml.dump(self.configuration_data, config_file)

    @classmethod
    def list_existing_files(cls) -> List[Path]:
        config_glob = str(cls.FOLDER_PATH.joinpath("config-*.toml"))
        return [Path(file_path) for file_path in glob.glob(config_glob)]

    @classmethod
    def get_available_configurations(cls):
        configurations = []
        for config_file_path in cls.list_existing_files():
            try:
                configurations.append(cls.load(config_file_path))
            except (ValueError, KeyError) as exc:
                log.warn(f"Failed to load {config_file_path} as configuration file: {exc}")

        return configurations

    @classmethod
    def load(cls, file_path: Path):
        file_name, _ = os.path.splitext(os.path.basename(file_path))

        _, _, network_name = file_name.split("-")

        with file_path.open() as config_file:
            data = toml.load(config_file)
            keystore_file_path = Account.find_keystore_file_path(
                data["address"], Path(data["keystore-path"])
            )
            return cls(
                account_filename=keystore_file_path,
                ethereum_client_rpc_endpoint=data["eth-rpc-endpoint"],
                network=Network.get_by_name(network_name),
                routing_mode=data["routing-mode"],
                enable_monitoring=data["enable-monitoring"],
                _initial_funding_txhash=data.get("_initial_funding_txhash"),
            )

    @classmethod
    def get_by_filename(cls, file_name):
        file_path = cls.FOLDER_PATH.joinpath(file_name)

        if not file_path.exists():
            raise ValueError(f"{file_path} is not a valid configuration file path")

        return cls.load(file_path)

    @classmethod
    def get_ethereum_rpc_endpoints(cls):
        endpoints = []

        config_glob = glob.glob(cls.FOLDER_PATH.joinpath("*.toml"))
        for config_file_path in config_glob:
            with open(config_file_path) as config_file:
                data = toml.load(config_file)
                endpoints.append(EthereumRPCProvider.make_from_url(data["eth-rpc-endpoint"]))
        return endpoints
