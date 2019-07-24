import unittest
import tempfile
from pathlib import Path

from raiden_installer import base


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        base.Account.KEYSTORE_FOLDER = tempfile.gettempdir()

        self.account = base.Account.create(passphrase="test_password")

    def test_account_can_get_address(self):
        self.assertIsNotNone(self.account.address)

    def test_can_not_get_private_key_without_passphrase(self):
        empty_account = base.Account("/invalid_folder")

        with self.assertRaises(ValueError):
            empty_account.private_key

    def test_can_get_web3_provider(self):
        web3_provider = self.account.get_web3_provider("http://localhost:8545")
        self.assertIsNotNone(web3_provider)

    def tearDown(self):
        self.account.keystore_file_path.unlink()


@unittest.skip("Still need to make mock functions for w3")
class RaidenConfigurationTestCase(unittest.TestCase):
    def setUp(self):
        temp_folder_path = Path(tempfile.gettempdir())
        base.RaidenConfigurationFile.FOLDER_PATH = temp_folder_path

        self.account = base.Account.create(passphrase="test_raiden_config")
        self.network = base.Network.get_by_name("goerli")
        self.ethereum_client_rpc_endpoint = "http://localhost:8545"
        self.token = base.Token(self.ethereum_client_rpc_endpoint, self.account)

        self.configuration_file = base.RaidenConfigurationFile(
            account=self.account,
            network=self.network,
            ethereum_client_rpc_endpoint=self.ethereum_client_rpc_endpoint,
            token=self.token,
        )

        passphrase_file = base.PassphraseFile(
            self.configuration_file.passphrase_file_path
        )
        passphrase_file.store(self.account.passphrase)

    def test_can_save_configuration(self):
        self.configuration_file.save()
        self.assertTrue(self.configuration_file.path.exists())

    def test_can_create_configuration(self):
        self.configuration_file.save()
        all_configs = base.RaidenConfigurationFile.get_available_configurations()
        self.assertEqual(len(all_configs), 1)

    def tearDown(self):
        for config in base.RaidenConfigurationFile.get_available_configurations():
            config.passphrase_file_path.unlink()
            config.path.unlink()
