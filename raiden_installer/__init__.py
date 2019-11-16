import os
import sys
from dataclasses import dataclass
from pathlib import Path

import structlog
import toml

log = structlog.get_logger()


ROOT_FOLDER = Path(__file__).resolve().parent.parent


@dataclass
class TokenSettings:
    sticker: str
    amount_required: int


@dataclass
class Settings:
    network: str
    client_release_channel: str
    client_release_version: str
    services_version: str
    ethereum_amount_required: int
    service_token: TokenSettings
    transfer_token: TokenSettings


def get_resource_folder_path():
    # Find absolute path for non-code resources (static files, templates,
    # configuration files) When we are running in development, it will just be
    # the same resources folder at the root path. When bundled by pyinstaller,
    # it will be placed on the folder indicated by sys._MEIPASS

    root_folder = getattr(sys, "_MEIPASS", ROOT_FOLDER)
    return os.path.join(root_folder, "resources")


_CONFIGURATION_FILE_NAME = os.path.join(get_resource_folder_path(), "conf", "settings.toml")

configuration_data = toml.load(_CONFIGURATION_FILE_NAME)

service_token_settings = TokenSettings(**configuration_data["service_token"])
transfer_token_settings = TokenSettings(**configuration_data["transfer_token"])

configuration_data.update(
    dict(service_token=service_token_settings, transfer_token=transfer_token_settings)
)

settings = Settings(**configuration_data)
