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

    Intended for testnet use only with throwaway keystore account
    and pwd.
    '''
    def __init__(self, dest_dir: str, keystore_pwd: str):
        self.dest_dir = dest_dir
        self.keystore_pwd = keystore_pwd
        self.pwd_file = None

    def create_plain_txt_pwd_file(self):
        pwd_file = Path(self.dest_dir).joinpath('pwd.txt')

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
    dest_dir: str,
    eth_rpc: str,
    address: str,
    user_deposit_address: str
) -> str:
    try:
        # Grab the network from the ETH RPC endpoint URL
        network = re.findall(r'(?<=//).*(?=.infura)', eth_rpc)[0]
    except IndexError as err:
        print('ETH RPC endpoint is not a valid Infura URL')
    else:
        config_file = Path(dest_dir).joinpath('config.toml')
        keystore = Path(dest_dir).joinpath('keystore')
        pwd_file = Path(dest_dir).joinpath('pwd.txt')
        
        toml_data = {
            "environment-type": "development",
            "keystore-path": keystore,
            "address": to_checksum_address(address),
            "password-file": pwd_file,
            "user-deposit-contract-address": user_deposit_address,
            "network-id": network,
            "accept-disclaimer": True,
            "eth-rpc-endpoint": eth_rpc,
            "routing-mode": "pfs",
            "pathfinding-service-address": (
                f'https://pfs-{network}.services-dev.raiden-network'
            ),
            "enable-monitoring": True
        }

        with open(config_file, 'w') as f:
            toml.dump(toml_data, f)

        return config_file