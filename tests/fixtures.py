from typing import Callable

import pytest
from tests.constants import TESTING_KEYSTORE_FOLDER

from raiden_installer.account import Account


@pytest.fixture
def test_password():
    return "test_password"


@pytest.fixture
def create_account(monkeypatch, test_password) -> Callable[[], Account]:
    accounts = list()

    def _create_account():
        account = Account.create(TESTING_KEYSTORE_FOLDER, test_password)
        accounts.append(account)
        return account

    yield _create_account

    for account in accounts:
        account.keystore_file_path.unlink()
