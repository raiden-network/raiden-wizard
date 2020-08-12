import json
import stat
import tempfile
import unittest
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import make_web3_provider
from raiden_installer.network import Network

TESTING_KEYSTORE_FOLDER = Path(tempfile.gettempdir()).joinpath("raiden-wizard-testing")


class AccountBaseTestCase(unittest.TestCase):
    def setUp(self):
        self.passphrase = "test_password"
        self.account = Account.create(TESTING_KEYSTORE_FOLDER, self.passphrase)

    def tearDown(self):
        try:
            self.account.keystore_file_path.unlink()
        except FileNotFoundError:
            pass


class AccountTestCase(AccountBaseTestCase):
    def test_account_can_get_address(self):
        self.assertIsNotNone(self.account.address)

    def test_load_user_accounts(self):
        accounts = Account.get_user_accounts(TESTING_KEYSTORE_FOLDER)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].address, self.account.address)
        self.assertEqual(accounts[0].keystore_file_path, self.account.keystore_file_path)

    def test_finding_keystore_file_path(self):
        path = Account.find_keystore_file_path(self.account.address, TESTING_KEYSTORE_FOLDER)
        self.assertEqual(path, self.account.keystore_file_path)

    def test_cannot_find_keystore_in_non_existent_directory(self):
        path = TESTING_KEYSTORE_FOLDER.joinpath("non", "existent", "path")
        keystore_file_path = Account.find_keystore_file_path(
            self.account.address, path
        )
        self.assertIsNone(keystore_file_path)

    def test_cannot_find_non_existent_keyfile(self):
        self.account.keystore_file_path.unlink()
        keystore_file_path = Account.find_keystore_file_path(
            self.account.address, TESTING_KEYSTORE_FOLDER
        )
        self.assertIsNone(keystore_file_path)

    def test_cannot_find_keyfile_without_read_permission(self):
        self.account.keystore_file_path.chmod(0)
        keystore_file_path = Account.find_keystore_file_path(
            self.account.address, TESTING_KEYSTORE_FOLDER
        )
        self.assertIsNone(keystore_file_path)

    def test_cannot_find_keyfile_with_invalid_content(self):
        with self.account.keystore_file_path.open("w") as keyfile:
            json.dump(dict(invalid="keyfile"), keyfile)
        keystore_file_path = Account.find_keystore_file_path(
            self.account.address, TESTING_KEYSTORE_FOLDER
        )
        self.assertIsNone(keystore_file_path)

    def test_cannot_find_keyfile_with_non_json_content(self):
        with self.account.keystore_file_path.open("w") as keyfile:
            keyfile.write("This is no JSON")
        keystore_file_path = Account.find_keystore_file_path(
            self.account.address, TESTING_KEYSTORE_FOLDER
        )
        self.assertIsNone(keystore_file_path)

    def test_has_no_content_when_keystore_file_does_not_exist(self):
        path = TESTING_KEYSTORE_FOLDER.joinpath("non", "existent", "path")
        account = Account(path)
        self.assertIsNone(account.content)

    def test_can_get_web3_provider(self):
        web3_provider = make_web3_provider("http://localhost:8545", self.account)
        self.assertIsNotNone(web3_provider)

    def test_cannot_run_funding_on_mainnet(self):
        network = Network.get_by_name("mainnet")
        with self.assertRaises(NotImplementedError):
            network.fund(self.account)


class LockedAccountTestCase(AccountBaseTestCase):
    def setUp(self):
        super().setUp()
        keystore_file_path = self.account.keystore_file_path
        self.locked_account = Account(keystore_file_path)

    def test_cannot_get_private_key_without_passphrase(self):
        with self.assertRaises(ValueError):
            self.locked_account.private_key

    def test_can_unlock_private_key(self):
        self.locked_account.unlock(self.passphrase)
        try:
            self.locked_account.private_key
        except ValueError:
            self.fail("should have unlocked private key")

    def test_cannot_unlock_with_wrong_password(self):
        with self.assertRaises(ValueError):
            self.locked_account.unlock("wrong" + self.passphrase)


class AccountCreationTestCase(unittest.TestCase):
    def setUp(self):
        self.account = Account.create(TESTING_KEYSTORE_FOLDER)

    def test_create_account_with_random_password(self):
        self.assertIsNotNone(self.account.passphrase)
        self.assertGreater(len(self.account.passphrase), 0)

    def tearDown(self):
        self.account.keystore_file_path.unlink()
