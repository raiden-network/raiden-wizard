#!/usr/bin/env python

import os
import unittest
import tempfile
import time

from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import make_web3_provider, Infura
from raiden_installer.network import Network
from raiden_installer.token_exchange import CustomTokenNetwork
from raiden_installer.tokens import EthereumAmount, Wei


INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")


@unittest.skipIf(INFURA_PROJECT_ID is None, "missing configuration for infura")
class IntegrationTestCase(unittest.TestCase):
    NETWORK_NAME = None

    def setUp(self):
        Account.DEFAULT_KEYSTORE_FOLDER = tempfile.gettempdir()
        self.account = Account.create("test_raiden_integration")
        self.network = Network.get_by_name(self.__class__.NETWORK_NAME)
        self.infura = Infura.make(self.network, INFURA_PROJECT_ID)
        self.w3 = make_web3_provider(self.infura.url, self.account)

    def tearDown(self):
        self.account.keystore_file_path.unlink()


class GoerliTestCase(IntegrationTestCase):
    NETWORK_NAME = "goerli"

    def test_goerli_faucet(self):
        TIMEOUT = 10
        INTERVAL = 1
        time_remaining = TIMEOUT
        self.network.fund(self.account)

        balance = EthereumAmount(Wei(0))
        while time_remaining > 0 or balance.amount == 0:
            balance = self.account.get_ethereum_balance(self.w3)
            time.sleep(INTERVAL)
            time_remaining -= INTERVAL

        self.assertTrue(balance.amount > 0, f"After {TIMEOUT} seconds, balance was not updated")


class TokenTestCase(IntegrationTestCase):
    NETWORK_NAME = "goerli"

    def setUp(self):
        super().setUp()
        self.token_network = CustomTokenNetwork(w3=self.w3, account=self.account)

    def test_can_not_mint_tokens_without_gas(self):
        with self.assertRaises(ValueError):
            self.token_network.mint(self.token_network.TOKEN_AMOUNT)

    def test_can_mint_tokens(self):
        self.network.fund(self.account)
        self.token_network.mint(self.token_network.TOKEN_AMOUNT)


if __name__ == "__main__":
    unittest.main()
