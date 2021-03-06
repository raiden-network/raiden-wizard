import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import structlog
import toml

log = structlog.get_logger()


ROOT_FOLDER = Path(__file__).resolve().parent.parent


@dataclass
class TokenSettings:
    ticker: str
    amount_required: int
    swap_amount: int
    mintable: bool = False


@dataclass
class Settings:
    name: str  # basename (without file extension) of the corresponding toml file
    network: str
    client_release_channel: str
    client_release_version: str
    services_version: str
    service_token: TokenSettings
    transfer_token: TokenSettings
    ethereum_amount_required: int
    ethereum_amount_required_after_swap: int = 0
    routing_mode: str = "pfs"
    monitoring_enabled: bool = True
    # matrix_server and pfs address are only used if client_release_channel = "demo_env"
    matrix_server: str = ""
    pathfinding_service_address: str = ""


def get_resource_folder_path():
    # Find absolute path for non-code resources (static files, templates,
    # configuration files) When we are running in development, it will just be
    # the same resources folder at the root path. When bundled by pyinstaller,
    # it will be placed on the folder indicated by sys._MEIPASS

    root_folder = getattr(sys, "_MEIPASS", ROOT_FOLDER)
    return os.path.join(root_folder, "resources")


@lru_cache()
def load_settings(settings_name):
    configuration_file = os.path.join(get_resource_folder_path(), "conf", f"{settings_name}.toml")
    configuration_data = toml.load(configuration_file)

    service_token_settings = TokenSettings(**configuration_data["service_token"])
    transfer_token_settings = TokenSettings(**configuration_data["transfer_token"])

    configuration_data.update(
        dict(service_token=service_token_settings, transfer_token=transfer_token_settings)
    )

    return Settings(name=settings_name, **configuration_data)
