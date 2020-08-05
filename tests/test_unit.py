#!/usr/bin/env python
import unittest
import tempfile
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.tokens import EthereumAmount, TokenAmount, Erc20Token, Wei


class TokenAmountTestCase(unittest.TestCase):
    def setUp(self):
        self.one_eth = EthereumAmount(1)
        self.one_rdn = TokenAmount(1, Erc20Token.find_by_ticker("RDN"))
        self.one_gwei = EthereumAmount(Wei(10 ** 9))
        self.almost_one_eth = EthereumAmount("0.875")
        self.some_wei = EthereumAmount(Wei(50_000))

    def test_can_convert_to_wei(self):
        self.assertEqual(self.one_eth.as_wei, Wei(10 ** 18))

    def test_can_multiply_amounts(self):
        two_eth_in_wei = 2 * self.one_eth.as_wei

        self.assertEqual(two_eth_in_wei, Wei(2 * 10 ** 18))

    def test_can_get_token_ticker(self):
        self.assertEqual(self.one_rdn.ticker, "RDN")

    def test_can_get_formatted_amount(self):
        self.assertEqual(self.one_eth.formatted, "1 ETH")
        self.assertEqual(self.one_rdn.formatted, "1 RDN")
        self.assertEqual(self.one_gwei.formatted, "1 GWEI")
        self.assertEqual(self.almost_one_eth.formatted, "0.875 ETH")
        self.assertEqual(self.some_wei.formatted, "50000 WEI")


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


class EthereumRpcProviderTestCase(unittest.TestCase):
    def test_infura_is_valid_project_id_or_endpoint(self):
        valid = [
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc0658db9b2",
            "36b457de4c103495ada08dc0658db9c3",
            "ropsten.infura.io/v3/8dc0658db9c34c103495a4a8b145e83a",
            "ropsten.infura.io/v4/8dc0658db9c34c103495a4a8b145e83a",
        ]
        invalid = [
            "not-infura.net/a7a347de4c103495a4a88dc0658db9b2",
            "7a347de4c103495a4a88dc0658db9b2",
            "a7a347de4c103495a4a88dc0658db9b2444",
            "a7a347de4c103495a4a88gc044658db9b2",
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc065gdb9b2",
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc044658db9b2",
            "goerli.infura.io/v3/a7a34c103495a4a88dc044658db9b2",
        ]
        for project_id in valid:
            self.assertTrue(Infura.is_valid_project_id_or_endpoint(project_id))
        for project_id in invalid:
            self.assertFalse(Infura.is_valid_project_id_or_endpoint(project_id))


if __name__ == "__main__":
    unittest.main()
