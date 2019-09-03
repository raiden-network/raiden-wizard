#!/usr/bin/env python

import os
import unittest
import hashlib
import tempfile
import platform

from eth_utils import to_checksum_address

from raiden_installer.base import log
from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.token_exchange import RaidenToken, Kyber, Uniswap
from raiden_installer.typing import ETH_UNIT


INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")
TEST_ACCOUNT_PRIVATE_KEY = os.getenv("TEST_RAIDEN_INSTALLER_ACCOUNT_PRIVATE_KEY")
TEST_ACCOUNT_PASSPHRASE = os.getenv("TEST_RAIDEN_INSTALLER_ACCOUNT_PASSPHRASE", "manual_testing")
ETHEREUM_NETWORK_NAME = os.getenv("TEST_RAIDEN_INSTALLER_ETHEREUM_NETWORK", "goerli")


class TestAccount(Account):
    @classmethod
    def generate_private_key(cls):
        """ Generates a deterministic private key (or takes the one from env vars) """
        if TEST_ACCOUNT_PRIVATE_KEY:
            return TEST_ACCOUNT_PRIVATE_KEY

        hsh = hashlib.sha256()
        hsh.update(
            "".join(
                str(it)
                for it in [
                    platform.node(),
                    platform.machine(),
                    platform.processor(),
                    platform.system(),
                ]
            ).encode()
        )
        return hsh.digest()


@unittest.skipIf(INFURA_PROJECT_ID is None, "missing configuration for infura")
class BaseTestCase(unittest.TestCase):
    NETWORK_NAME = ETHEREUM_NETWORK_NAME

    def setUp(self):
        TestAccount.DEFAULT_KEYSTORE_FOLDER = tempfile.gettempdir()
        self.account = TestAccount.create(TEST_ACCOUNT_PASSPHRASE)
        self.network = Network.get_by_name(self.NETWORK_NAME)
        self.infura = Infura.make(self.network, INFURA_PROJECT_ID)
        self.w3 = make_web3_provider(self.infura.url, self.account)

    def _wait_for_ethereum_funds(self, timeout=60):
        return self.account.wait_for_ethereum_funds(self.w3, self.network, timeout=timeout)

    def tearDown(self):
        self.account.keystore_file_path.unlink()


class GoerliTestCase(BaseTestCase):
    NETWORK_NAME = "goerli"

    def test_goerli_faucet(self):
        TIMEOUT = 30
        self.network.fund(self.account)

        balance = self._wait_for_ethereum_funds(timeout=TIMEOUT)
        self.assertTrue(balance > 0, f"After {TIMEOUT} seconds, balance was not updated")


class TokenSwapTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.rdn = RaidenToken(w3=self.w3, account=self.account)
        self.ethereum_amount = self.network.MINIMUM_ETHEREUM_BALANCE_REQUIRED

    def _ensure_ethereum_funds(self):
        current_balance = self.account.get_ethereum_balance(self.w3)
        log.debug(f"Current ETH balance: {current_balance}")

        if current_balance < self.ethereum_amount:
            needed_funds = self.ethereum_amount - current_balance
            print(
                f"Please send at least {needed_funds} to {self.account.address} on "
                f"{self.network.capitalized_name}"
            )
            return self._wait_for_ethereum_funds(timeout=120)


class KyberExchangeTestCase(TokenSwapTestCase):
    NETWORK_NAME = "ropsten"

    def test_rdn_swap(self):
        self._ensure_ethereum_funds()
        log.debug(f"RDN balance is {self.rdn.balance}")
        kyber = Kyber(w3=self.w3, account=self.account)
        exchange_rate = kyber.get_current_rate(self.ethereum_amount)
        log.debug(f"Kyber exchange rate: {exchange_rate} maximum")
        kyber.swap_ethereum_for_rdn(self.ethereum_amount, exchange_rate)
        log.debug(f"RDN balance after swap is {self.rdn.balance} RDN")


class UniswapExchangeRDNTestCase(TokenSwapTestCase):
    NETWORK_NAME = "mainnet"

    def test_swap(self):
        self._ensure_ethereum_funds()
        log.debug(f"RDN balance is {self.rdn.balance}")
        uniswap = Uniswap(w3=self.w3, account=self.account)
        exchange_rate = uniswap.get_current_rate(self.ethereum_amount)
        uniswap.swap_ethereum_for_rdn(self.ethereum_amount, exchange_rate)
        log.debug(f"RDN balance after swap is {self.rdn.balance}")

    def test_gas_estimate(self):
        ETH_AMOUNT = ETH_UNIT(0.01)
        wei_amount = int(ETH_AMOUNT * (10 ** 18))
        uniswap = Uniswap(w3=self.w3, account=self.account)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + uniswap.EXCHANGE_TIMEOUT
        exchange_rate = uniswap.get_current_rate(ETH_AMOUNT)

        transaction_params = {
            "from": self.w3.eth.defaultAccount,
            "value": wei_amount,
            "nonce": self.w3.eth.getTransactionCount(self.w3.eth.defaultAccount),
        }

        exchange_proxy = uniswap.get_exchange_proxy("RDN")
        token_amount = uniswap._get_tokens_available("RDN", ETH_AMOUNT)
        transaction = exchange_proxy.functions.ethToTokenSwapInput(
            token_amount, deadline
        ).buildTransaction(transaction_params)
        estimated_gas = self.w3.eth.estimateGas(transaction)

        print(estimated_gas)


class UniswapExchangeDAITestCase(TokenSwapTestCase):
    NETWORK_NAME = "rinkeby"

    def test_swap(self):
        log.debug(f"Making ETH <-> DAI swap for {self.account.address}")
        self._ensure_ethereum_funds()
        uniswap = Uniswap(w3=self.w3, account=self.account)
        dai = uniswap.get_token("DAI")
        log.debug(f"Before swap, balance is {dai.balance} DAI")
        dai_exchange_rate = uniswap._get_exchange_rate("DAI", self.ethereum_amount)
        uniswap._run_token_swap("DAI", self.ethereum_amount, dai_exchange_rate)
        log.debug(f"After swap, balance is {dai.balance} DAI")

    def test_gas_estimate(self):
        ETH_AMOUNT = ETH_UNIT(1)
        wei_amount = int(ETH_AMOUNT * (10 ** 18))
        uniswap = Uniswap(w3=self.w3, account=self.account)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + uniswap.EXCHANGE_TIMEOUT

        dai = uniswap.get_token("DAI")
        dai_exchange_rate = uniswap._get_exchange_rate("DAI", self.ethereum_amount)

        transaction_params = {
            "chainId": int(self.w3.net.version),
            "from": self.w3.eth.defaultAccount,
            "value": wei_amount,
            "nonce": self.w3.eth.getTransactionCount(self.w3.eth.defaultAccount),
        }

        exchange_proxy = uniswap.get_exchange_proxy("DAI")
        token_amount = exchange_proxy.functions.getEthToTokenInputPrice(
            transaction_params["value"]
        ).call()

        transaction = exchange_proxy.functions.ethToTokenSwapInput(
            token_amount, deadline
        ).buildTransaction(transaction_params)
        estimated_gas = self.w3.eth.estimateGas(transaction)

        print(estimated_gas)


class ExchangeSelectionTestCase(TokenSwapTestCase):
    NETWORK_NAME = "mainnet"

    ETHEREUM_AMOUNTS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1, 1.5)

    def setUp(self):
        super().setUp()
        self.kyber = Kyber(w3=self.w3, account=self.account)
        self.uniswap = Uniswap(w3=self.w3, account=self.account)

    def test_can_get_rates(self):
        print("\t".join([st.rjust(21) for st in ("ETH Sold", "Kyber", "Uniswap")]))

        for eth_amount in self.ETHEREUM_AMOUNTS:
            kyber_rate = self.kyber.get_current_rate(ETH_UNIT(eth_amount))
            uniswap_rate = self.uniswap.get_current_rate(ETH_UNIT(eth_amount))
            print(
                "\t".join(
                    [
                        st.rjust(21)
                        for st in (f"{eth_amount}", f"{kyber_rate:0.8f}", f"{uniswap_rate:0.8f}")
                    ]
                )
            )


if __name__ == "__main__":
    unittest.main()
