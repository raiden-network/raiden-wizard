import os
import re
from pathlib import Path


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
    Builds the RPC endpoint URL for chosen network
    '''
    try:
        # Check whether proj_id matches a hexadecimal string
        proj_id = re.match(r'^[a-fA-F0-9]+$', proj_id.strip())[0]

        eth_rpc = f'https://{network}.infura.io/v3/{proj_id}'
        return eth_rpc
    except TypeError as err:
        print('Not a valid project ID')