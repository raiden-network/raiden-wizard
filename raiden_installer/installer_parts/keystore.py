import os
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from eth_keyfile import create_keyfile_json


def generate_keyfile_name() -> str:
    now = datetime.utcnow()
    now_formatted = now.replace(microsecond=0).isoformat().replace(':', '-')

    keyfile_name = f'UTC--{now_formatted}Z--{uuid4()!s}'
    return keyfile_name


def make_keystore(dest_dir: str, keyfile_name: str, keystore_pwd: str) -> dict:
    '''
    Creates a keystore directory with a
    passphrase encrypted keystore file.
    '''
    keystore = Path(dest_dir).joinpath('keystore')
    keystore.mkdir(exist_ok=True)

    keyfile = Path(keystore).joinpath(keyfile_name)
    keyfile_content = create_keyfile_json(os.urandom(32), keystore_pwd.encode())

    with open(keyfile, 'w') as f:
        json.dump(keyfile_content, f)

    return keyfile_content