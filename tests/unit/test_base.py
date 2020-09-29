import unittest

from tests.constants import TESTING_KEYSTORE_FOLDER, TESTING_TEMP_FOLDER

from raiden_installer import load_settings
from raiden_installer.account import Account
from raiden_installer.base import PassphraseFile, RaidenConfigurationFile
from raiden_installer.network import Network


class PassphraseFileTestCase(unittest.TestCase):
    def setUp(self):
        self.file_path = TESTING_TEMP_FOLDER.joinpath("passphrase")
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
        RaidenConfigurationFile.FOLDER_PATH = TESTING_TEMP_FOLDER.joinpath("config")

        self.account = Account.create(TESTING_KEYSTORE_FOLDER, passphrase="test_raiden_config")
        self.network = Network.get_by_name("goerli")
        self.settings = load_settings("demo_env")

        self.configuration_file = RaidenConfigurationFile(
            self.account.keystore_file_path,
            self.settings,
            "http://localhost:8545",
        )

    def test_can_save_configuration(self):
        self.configuration_file.save()
        self.assertTrue(self.configuration_file.path.exists())

    def test_can_create_configuration(self):
        self.configuration_file.save()
        all_configs = RaidenConfigurationFile.get_available_configurations(self.settings)
        self.assertEqual(len(all_configs), 1)

    def test_can_get_by_filename(self):
        self.configuration_file.save()
        try:
            RaidenConfigurationFile.get_by_filename(self.configuration_file.file_name)
        except ValueError:
            self.fail("should load configuration by file name")

    def test_cannot_get_by_not_existing_filename(self):
        with self.assertRaises(ValueError):
            RaidenConfigurationFile.get_by_filename("invalid")

    def test_cannot_get_config_for_different_settings(self):
        self.configuration_file.save()
        settings = load_settings("mainnet")
        all_configs = RaidenConfigurationFile.get_available_configurations(settings)
        self.assertEqual(len(all_configs), 0)

    def tearDown(self):
        for config in RaidenConfigurationFile.get_available_configurations(self.settings):
            config.path.unlink()
        self.account.keystore_file_path.unlink()
