from datetime import datetime
from uuid import uuid4


def generate_keyfile_name() -> str:
    now = datetime.utcnow()
    now_formatted = now.replace(microsecond=0).isoformat().replace(':', '-')

    keyfile_name = f'UTC--{now_formatted}Z--{uuid4()!s}'
    return keyfile_name