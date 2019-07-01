import os
import re
import toml
from pathlib import Path
from eth_utils import to_checksum_address


class PlainTxtPwd:
    '''
    Provides a method for storing the keystore pwd in a plain txt
    file which is necessary when initializing Raiden and a method
    for deleting that very same file.
    '''
    def __init__(self, config_dir: Path, keystore_pwd: str) -> None:
        self.config_dir = config_dir
        self.keystore_pwd = keystore_pwd
        self.pwd_file = None

    def create_plain_txt_pwd_file(self):
        pwd_file = Path(self.config_dir).joinpath('pwd.txt')

        with open(pwd_file, 'w') as f:
            f.write(self.keystore_pwd)

        self.pwd_file = pwd_file

    def delete_plain_txt_pwd_file(self):
        try:
            os.remove(self.pwd_file)
            self.pwd_file = None
        except (TypeError, FileNotFoundError) as err:
            print('No password file to delete')


def eth_rpc_endpoint(proj_id: str, network: str) -> str:
    '''
    Builds the ETH RPC endpoint URL for chosen network
    '''
    try:
        # Check whether proj_id matches a hexadecimal string
        proj_id = re.match(r'^[a-fA-F0-9]+$', proj_id.strip())[0]

        eth_rpc = f'https://{network}.infura.io/v3/{proj_id}'
        return eth_rpc
    except TypeError as err:
        print('Not a valid project ID')


def generate_raiden_config_file(
    config_dir: Path,
    keystore_dir: Path,
    eth_rpc: str,
    address: str,
    user_deposit_address: str
) -> Path:
    try:
        # Grab the network from the ETH RPC endpoint URL
        network = re.findall(r'(?<=//).*(?=.infura)', eth_rpc)[0]
    except IndexError as err:
        print('ETH RPC endpoint is not a valid Infura URL')
    else:
        config_file = Path(config_dir).joinpath('config.toml')
        pwd_file = Path(config_dir).joinpath('pwd.txt')
        keystore = Path(keystore_dir).joinpath('keystore')
        
        toml_data = {
            "environment-type": "development",
            "keystore-path": str(keystore),
            "address": to_checksum_address(address),
            "password-file": str(pwd_file),
            "user-deposit-contract-address": user_deposit_address,
            "network-id": network,
            "accept-disclaimer": True,
            "eth-rpc-endpoint": eth_rpc,
            "routing-mode": "pfs",
            "pathfinding-service-address": (
                f'https://pfs-{network}.services-dev.raiden.network'
            ),
            "enable-monitoring": True
        }

        with open(config_file, 'w') as f:
            toml.dump(toml_data, f)

        return config_file