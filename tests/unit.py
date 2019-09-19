#!/usr/bin/env python
import unittest
import tempfile
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.base import RaidenConfigurationFile, PassphraseFile
from raiden_installer.ethereum_rpc import make_web3_provider
from raiden_installer.network import Network
from raiden_installer.tokens import EthereumAmount, RDNAmount, Wei


class TokenAmountTestCase(unittest.TestCase):
    def setUp(self):
        self.one_eth = EthereumAmount(1)
        self.one_rdn = RDNAmount(1)
        self.one_gwei = EthereumAmount(Wei(10 ** 9))
        self.almost_one_eth = EthereumAmount("0.875")
        self.some_wei = EthereumAmount(Wei(50_000))

    def test_can_convert_to_wei(self):
        self.assertEqual(self.one_eth.as_wei, Wei(10 ** 18))

    def test_can_multiply_amounts(self):
        two_eth_in_wei = 2 * self.one_eth.as_wei

        self.assertEqual(two_eth_in_wei, Wei(2 * 10 ** 18))

    def test_can_get_token_sticker(self):
        self.assertEqual(self.one_rdn.sticker, "RDN")

    def test_can_get_formatted_amount(self):
        self.assertEqual(self.one_eth.formatted, "1 ETH")
        self.assertEqual(self.one_rdn.formatted, "1 RDN")
        self.assertEqual(self.one_gwei.formatted, "1 GWEI")
        self.assertEqual(self.almost_one_eth.formatted, "0.875 ETH")
        self.assertEqual(self.some_wei.formatted, "50000 WEI")


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        Account.DEFAULT_KEYSTORE_FOLDER = tempfile.gettempdir()

        self.account = Account.create(passphrase="test_password")

    def test_account_can_get_address(self):
        self.assertIsNotNone(self.account.address)

    def test_can_not_get_private_key_without_passphrase(self):
        empty_account = Account("/invalid_folder")

        with self.assertRaises(ValueError):
            empty_account.private_key

    def test_can_get_web3_provider(self):
        web3_provider = make_web3_provider("http://localhost:8545", self.account)
        self.assertIsNotNone(web3_provider)

    def tearDown(self):
        self.account.keystore_file_path.unlink()


class RaidenConfigurationTestCase(unittest.TestCase):
    def setUp(self):
        temp_folder_path = Path(tempfile.gettempdir())
        RaidenConfigurationFile.FOLDER_PATH = temp_folder_path

        self.account = Account.create(passphrase="test_raiden_config")
        self.network = Network.get_by_name("goerli")
        self.ethereum_client_rpc_endpoint = "http://localhost:8545"

        self.configuration_file = RaidenConfigurationFile(
            account=self.account,
            network=self.network,
            ethereum_client_rpc_endpoint=self.ethereum_client_rpc_endpoint,
        )

        passphrase_file = PassphraseFile(self.configuration_file.passphrase_file_path)
        passphrase_file.store(self.account.passphrase)

    def test_can_save_configuration(self):
        self.configuration_file.save()
        self.assertTrue(self.configuration_file.path.exists())

    def test_can_create_configuration(self):
        self.configuration_file.save()
        all_configs = RaidenConfigurationFile.get_available_configurations()
        self.assertEqual(len(all_configs), 1)

    def tearDown(self):
        for config in RaidenConfigurationFile.get_available_configurations():
            config.passphrase_file_path.unlink()
            config.path.unlink()


if __name__ == "__main__":
    unittest.main()
