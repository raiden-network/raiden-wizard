import tempfile
import unittest
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.base import RaidenConfigurationFile, PassphraseFile
from raiden_installer.network import Network

TESTING_KEYSTORE_FOLDER = Path(tempfile.gettempdir()).joinpath("raiden-wizard-testing")

class PassphraseFileTestCase(unittest.TestCase):
    def setUp(self):
        self.file_path = TESTING_KEYSTORE_FOLDER.joinpath("passphrase")
        self.passphrase_file = PassphraseFile(self.file_path)
    
    def test_store_and_retrieve_passphrase(self):
        password = "test_password"
        self.passphrase_file.store(password)
        self.assertEqual(self.passphrase_file.retrieve(), password)

    def tearDown(self):
        try:
            self.file_path.unlink()
        except FileNotFoundError:
            pass


class RaidenConfigurationTestCase(unittest.TestCase):
    def setUp(self):
        temp_folder_path = Path(tempfile.gettempdir())
        RaidenConfigurationFile.FOLDER_PATH = temp_folder_path

        self.account = Account.create(passphrase="test_raiden_config")
        self.network = Network.get_by_name("goerli")
        self.ethereum_client_rpc_endpoint = "http://localhost:8545"

        self.configuration_file = RaidenConfigurationFile(
            account_filename=self.account.keystore_file_path,
            network=self.network,
            ethereum_client_rpc_endpoint=self.ethereum_client_rpc_endpoint,
        )

    def test_can_save_configuration(self):
        self.configuration_file.save()
        self.assertTrue(self.configuration_file.path.exists())

    def test_can_create_configuration(self):
        self.configuration_file.save()
        all_configs = RaidenConfigurationFile.get_available_configurations()
        self.assertEqual(len(all_configs), 1)

    def tearDown(self):
        for config in RaidenConfigurationFile.get_available_configurations():
            config.path.unlink()
