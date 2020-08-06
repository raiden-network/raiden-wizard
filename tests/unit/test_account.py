import tempfile
import unittest
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import make_web3_provider


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        Account.DEFAULT_KEYSTORE_FOLDER = Path(tempfile.gettempdir())

        self.account = Account.create(passphrase="test_password")

    def test_account_can_get_address(self):
        self.assertIsNotNone(self.account.address)

    def test_can_not_get_private_key_without_passphrase(self):
        empty_account = Account(Path("/invalid_folder"))

        with self.assertRaises(ValueError):
            empty_account.private_key

    def test_can_get_web3_provider(self):
        web3_provider = make_web3_provider("http://localhost:8545", self.account)
        self.assertIsNotNone(web3_provider)

    def tearDown(self):
        self.account.keystore_file_path.unlink()
