import os
import json
from pathlib import Path
from datetime import datetime
import uuid

from eth_keyfile import create_keyfile_json, decode_keyfile_json
from xdg import XDG_DATA_HOME


class KeystoreError(Exception):
    pass


class KeystoreFile:
    FOLDER = XDG_DATA_HOME

    def __init__(self, file_path, passphrase):
        self.file_path = file_path
        self.passphrase = passphrase

    @property
    def content(self):
        with self.file_path.open() as f:
            return json.load(f)

    @property
    def can_decode(self):
        return False

    @property
    def get_private_key(self):
        return decode_keyfile_json(self.content, self.passphrase.encode())

    @property
    def is_setup(self):
        return os.path.exists(self.file_path) and self.can_decode

    @classmethod
    def get_keystore_files(cls):
        pass

    @classmethod
    def make_file_name(cls):
        timestamp = (
            datetime.utcnow().replace(microsecond=0).isoformat().replace(":", "-")
        )
        return f"UTC--{timestamp}Z--{uuid.uuid4()!s}"

    @classmethod
    def create(cls, passphrase, file_path=None):
        keystore_file_path = Path(file_path) or Path(cls.FOLDER).joinpath(
            cls.make_file_name()
        )

        if keystore_file_path.exists():
            raise KeystoreError(f"File {keystore_file_path} already exists")

        keystore_folder_path = Path(keystore_file_path).parent
        keystore_folder_path.mkdir(exists_ok=True)

        with keystore_file_path.open("w") as keyfile:
            encrypted_content = os.urandom(32), passphrase.encode()
            json.dump(create_keyfile_json(encrypted_content, keyfile))

        return cls(keystore_file_path, passphrase)
