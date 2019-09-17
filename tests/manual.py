#!/usr/bin/env python

import os
import unittest
import hashlib
import tempfile
import platform

from raiden_installer.base import log
from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.token_exchange import Kyber, Uniswap, RaidenTokenNetwork
from raiden_installer.tokens import EthereumAmount, RDNAmount, Wei


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

    def _wait_for_ethereum_funds(self, ethereum_amount: EthereumAmount, timeout=180):
        return self.account.wait_for_ethereum_funds(
            self.w3, ethereum_amount=ethereum_amount, timeout=timeout
        )

    def tearDown(self):
        self.account.keystore_file_path.unlink()


class TokenSwapTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.rdn = RaidenTokenNetwork(w3=self.w3, account=self.account)
        self.rdn_amount = RDNAmount(75)

    def _ensure_ethereum_funds(self, ethereum_amount: EthereumAmount):
        current_balance = self.account.get_ethereum_balance(self.w3)
        log.debug(f"Current balance: {current_balance.formatted}")

        if current_balance < ethereum_amount:
            needed_funds = EthereumAmount(Wei(ethereum_amount.as_wei - current_balance.as_wei))
            print(
                f"Please send at least {needed_funds.formatted} to 0x{self.account.address} on "
                f"{self.network.capitalized_name}"
            )
            return self._wait_for_ethereum_funds(ethereum_amount=needed_funds)

    def _execute_rdn_swap(self, exchange):
        log.debug(f"RDN balance is {self.rdn.balance}")
        swap_costs = exchange.calculate_transaction_costs(self.rdn_amount)
        exchange_rate = swap_costs["exchange_rate"]
        log.debug(f"{exchange.name} exchange rate: {exchange_rate.formatted} maximum")
        self._ensure_ethereum_funds(swap_costs["total"])
        exchange.buy_tokens(self.rdn_amount)
        log.debug(f"RDN balance after swap is {self.rdn.balance} RDN")


class KyberExchangeTestCase(TokenSwapTestCase):
    NETWORK_NAME = "ropsten"

    def test_swap(self):
        self._execute_rdn_swap(Kyber(w3=self.w3, account=self.account))


class UniswapExchangeRDNTestCase(TokenSwapTestCase):
    NETWORK_NAME = "mainnet"

    def test_swap(self):
        self._execute_rdn_swap(Uniswap(w3=self.w3, account=self.account))

    def test_gas_estimate(self):
        uniswap = Uniswap(w3=self.w3, account=self.account)
        costs = uniswap.calculate_transaction_costs(self.rdn_amount)
        print(costs["gas"])


# class UniswapExchangeDAITestCase(TokenSwapTestCase):
#     NETWORK_NAME = "rinkeby"

#     def test_swap(self):
#         log.debug(f"Making ETH <-> DAI swap for {self.account.address}")
#         self._ensure_ethereum_funds()
#         uniswap = Uniswap(w3=self.w3, account=self.account)
#         dai = uniswap.get_token("DAI")
#         log.debug(f"Before swap, balance is {dai.balance} DAI")
#         dai_exchange_rate = uniswap._get_exchange_rate("DAI", self.ethereum_amount)
#         uniswap._run_token_swap("DAI", self.ethereum_amount, dai_exchange_rate)
#         log.debug(f"After swap, balance is {dai.balance} DAI")

#     def test_gas_estimate(self):
#         one_eth = EthereumAmount(Eth(1))
#         uniswap = Uniswap(w3=self.w3, account=self.account)
#         latest_block = self.w3.eth.getBlock("latest")
#         deadline = latest_block.timestamp + uniswap.EXCHANGE_TIMEOUT

#         transaction_params = {
#             "chainId": int(self.w3.net.version),
#             "from": self.w3.eth.defaultAccount,
#             "value": one_eth.as_wei,
#             "nonce": self.w3.eth.getTransactionCount(self.w3.eth.defaultAccount),
#         }

#         exchange_proxy = uniswap.get_exchange_proxy("DAI")
#         token_amount = exchange_proxy.functions.getEthToTokenInputPrice(
#             transaction_params["value"]
#         ).call()

#         transaction = exchange_proxy.functions.ethToTokenSwapInput(
#             token_amount, deadline
#         ).buildTransaction(transaction_params)
#         estimated_gas = self.w3.eth.estimateGas(transaction)

#         print(estimated_gas)


class ExchangeSelectionTestCase(TokenSwapTestCase):
    NETWORK_NAME = "mainnet"

    TOKEN_AMOUNTS = (50, 75, 100, 150, 200, 300, 500, 1000)

    def setUp(self):
        super().setUp()
        self.kyber = Kyber(w3=self.w3, account=self.account)
        self.uniswap = Uniswap(w3=self.w3, account=self.account)

    def test_can_get_costs(self):
        print("\t".join([st.rjust(36) for st in ("RDN to buy", "Kyber", "Uniswap")]))

        for amount in self.TOKEN_AMOUNTS:
            rdn_amount = RDNAmount(amount)
            kyber_costs = self.kyber.calculate_transaction_costs(rdn_amount)
            uniswap_costs = self.uniswap.calculate_transaction_costs(rdn_amount)
            print(
                "\t".join(
                    [
                        st.rjust(36)
                        for st in (
                            f"{rdn_amount.formatted}",
                            f"{kyber_costs['total'].formatted}",
                            f"{uniswap_costs['total'].formatted}",
                        )
                    ]
                )
            )


if __name__ == "__main__":
    unittest.main()
