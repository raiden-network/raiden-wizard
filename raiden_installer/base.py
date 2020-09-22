import glob
import os
from pathlib import Path
from typing import List, Union

import toml
from eth_utils import to_checksum_address
from xdg import XDG_DATA_HOME

from raiden_installer import Settings, load_settings, log
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
        self, account_filename: Union[Path, str], settings: Settings, ethereum_client_rpc_endpoint: str, **kw
    ):
        self.account = Account(account_filename)
        self.account_filename = account_filename
        self.settings = settings
        self.network = Network.get_by_name(self.settings.network)
        self.ethereum_client_rpc_endpoint = ethereum_client_rpc_endpoint
        self.accept_disclaimer = kw.get("accept_disclaimer", True)
        self.enable_monitoring = kw.get("enable_monitoring", self.settings.monitoring_enabled)
        self.routing_mode = kw.get("routing_mode", self.settings.routing_mode)
        self.services_version = self.settings.services_version
        self._initial_funding_txhash = kw.get("_initial_funding_txhash")

    @property
    def configuration_data(self):
        base_config = {
            "environment-type": self.environment_type,
            "keystore-path": str(self.account.keystore_file_path.parent),
            "address": to_checksum_address(self.account.address),
            "network-id": self.network.name,
            "accept-disclaimer": self.accept_disclaimer,
            "eth-rpc-endpoint": self.ethereum_client_rpc_endpoint,
            "routing-mode": self.routing_mode,
            "enable-monitoring": self.enable_monitoring,
            "_initial_funding_txhash": self._initial_funding_txhash,
        }

        # If the config is for a demo-env we'll need to add/overwrite some settings
        if self.settings.client_release_channel == "demo_env":
            base_config.update(
                {
                    "matrix-server": self.settings.matrix_server,
                    "routing-mode": "pfs",
                    "pathfinding-service-address": self.settings.pathfinding_service_address,
                }
            )

        return base_config

    @property
    def environment_type(self):
        return "production" if self.network.name == "mainnet" else "development"

    @property
    def file_name(self):
        return f"config-{self.account.address}-{self.settings.name}.toml"

    @property
    def path(self):
        return self.FOLDER_PATH.joinpath(self.file_name)

    def save(self):
        self.FOLDER_PATH.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as config_file:
            toml.dump(self.configuration_data, config_file)

    @classmethod
    def list_existing_files(cls, settings: Settings) -> List[Path]:
        config_glob = str(cls.FOLDER_PATH.joinpath(f"config-*-{settings.name}.toml"))
        return [Path(file_path) for file_path in glob.glob(config_glob)]

    @classmethod
    def get_available_configurations(cls, settings: Settings):
        configurations = []
        for config_file_path in cls.list_existing_files(settings):
            try:
                configurations.append(cls.load(config_file_path))
            except (ValueError, KeyError) as exc:
                log.warn(f"Failed to load {config_file_path} as configuration file: {exc}")

        return configurations

    @classmethod
    def load(cls, file_path: Path):
        file_name, _ = os.path.splitext(os.path.basename(file_path))

        _, _, settings_name = file_name.split("-")

        try:
            settings = load_settings(settings_name)
        except FileNotFoundError as exc:
            raise ValueError(
                f"There are no Wizard settings {settings_name} for Raiden configuration {file_path}"
            )

        with file_path.open() as config_file:
            data = toml.load(config_file)
            keystore_file_path = Account.find_keystore_file_path(
                data["address"], Path(data["keystore-path"])
            )
            if keystore_file_path is None:
                raise ValueError(
                    f"{data['keystore-path']} does not contain the account file for config {file_path}"
                )
            return cls(
                account_filename=keystore_file_path,
                ethereum_client_rpc_endpoint=data["eth-rpc-endpoint"],
                settings=settings,
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
