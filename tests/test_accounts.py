import unittest
import tempfile

from raiden_installer.models import Account


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        Account.KEYSTORE_FOLDER = tempfile.gettempdir()

        self.account = Account.create(passphrase="test_password")

    def test_account_can_get_address(self):
        self.assertIsNotNone(self.account.address)

    def test_can_not_get_private_key_without_passphrase(self):
        empty_account = Account("/invalid_folder")

        with self.assertRaises(ValueError):
            empty_account.private_key

    def tearDown(self):
        self.account.keystore_file_path.unlink()
