from installer_parts import (
    keystore
)
from constants import (
    KEYSTORE_DIR
)


def set_up_keystore(keystore_password: str) -> dict:
    keyfile_name = keystore.generate_keyfile_name()
    keyfile = keystore.make_keystore(
        KEYSTORE_DIR,
        keyfile_name,
        keystore_password
    )
    keyfile_content = keystore.get_keyfile_content(keyfile)
    return keyfile_content