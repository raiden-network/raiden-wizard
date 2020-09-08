import os
import time
import unittest
from pathlib import Path

from tests.constants import TESTING_KEYSTORE_FOLDER
from tests.utils import empty_account

from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.tokens import Erc20Token, EthereumAmount, Wei
from raiden_installer.transactions import get_token_balance, mint_tokens
from raiden_installer.utils import wait_for_transaction

INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")


@unittest.skipIf(INFURA_PROJECT_ID is None, "missing configuration for infura")
class IntegrationTestCase(unittest.TestCase):
    NETWORK_NAME = "goerli"

    def setUp(self):
        assert INFURA_PROJECT_ID

        self.account = Account.create(TESTING_KEYSTORE_FOLDER, "test_raiden_integration")
        self.network = Network.get_by_name(self.__class__.NETWORK_NAME)
        self.infura = Infura.make(self.network, INFURA_PROJECT_ID)
        self.w3 = make_web3_provider(self.infura.url, self.account)

    def tearDown(self):
        empty_account(self.w3, self.account)
        self.account.keystore_file_path.unlink()


class GoerliTestCase(IntegrationTestCase):
    def test_goerli_faucet(self):
        TIMEOUT = 10
        INTERVAL = 1
        time_remaining = TIMEOUT
        self.network.fund(self.account)

        balance = EthereumAmount(Wei(0))
        while time_remaining > 0 or balance.as_wei == 0:
            balance = self.account.get_ethereum_balance(self.w3)
            time.sleep(INTERVAL)
            time_remaining -= INTERVAL

        self.assertTrue(balance.as_wei > 0, f"After {TIMEOUT} seconds, balance was not updated")


class TokenTestCase(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.svt_token = Erc20Token.find_by_ticker("SVT", self.NETWORK_NAME)

    def test_cannot_mint_tokens_without_gas(self):
        with self.assertRaises(ValueError):
            mint_tokens(w3=self.w3, account=self.account, token=self.svt_token)

    def test_can_mint_tokens(self):
        self.network.fund(self.account)
        self.account.wait_for_ethereum_funds(self.w3, EthereumAmount(0.01))
        tx_hash = mint_tokens(w3=self.w3, account=self.account, token=self.svt_token)
        wait_for_transaction(self.w3, tx_hash)
        balance = get_token_balance(self.w3, self.account, self.svt_token)
        self.assertTrue(balance.as_wei >= self.svt_token.supply)
