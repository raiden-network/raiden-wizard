#!/usr/bin/env python

import codecs
import hashlib
import os
import platform
import tempfile
import unittest
from pathlib import Path

from raiden_installer import settings, TokenSettings
from raiden_installer import log
from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.token_exchange import Kyber, Uniswap
from raiden_installer.tokens import EthereumAmount, TokenAmount, Erc20Token, Wei
from raiden_installer.transactions import mint_tokens, deposit_service_tokens, get_token_balance

from tests import override_settings


INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")
TEST_ACCOUNT_PRIVATE_KEY = os.getenv("TEST_RAIDEN_INSTALLER_ACCOUNT_PRIVATE_KEY")
TEST_ACCOUNT_PASSPHRASE = os.getenv("TEST_RAIDEN_INSTALLER_ACCOUNT_PASSPHRASE", "manual_testing")


GOERLI_SERVICE_TOKEN_SETTINGS = TokenSettings(sticker="RDN", amount_required=int(6e18))
ROPSTEN_SERVICE_TOKEN_SETTINGS = TokenSettings(sticker="RDN", amount_required=int(6e18))


class TestAccount(Account):
    @classmethod
    def generate_private_key(cls):
        """ Generates a deterministic private key (or takes the one from env vars) """
        if TEST_ACCOUNT_PRIVATE_KEY:
            return codecs.decode(TEST_ACCOUNT_PRIVATE_KEY.encode(), "hex")

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
    def setUp(self):
        TestAccount.DEFAULT_KEYSTORE_FOLDER = Path(tempfile.gettempdir())
        self.account = TestAccount.create(TEST_ACCOUNT_PASSPHRASE)

    def _get_network(self):
        return Network.get_by_name(settings.network)

    def _get_RDN(self):
        return Erc20Token.find_by_sticker("RDN")

    def _get_web3(self):
        assert INFURA_PROJECT_ID
        network = self._get_network()
        infura = Infura.make(network, INFURA_PROJECT_ID)
        return make_web3_provider(infura.url, self.account)

    def _wait_for_ethereum_funds(self, ethereum_amount: EthereumAmount, timeout=180):
        w3 = self._get_web3()
        return self.account.wait_for_ethereum_funds(
            w3, ethereum_amount=ethereum_amount, timeout=timeout
        )

    def tearDown(self):
        self.account.keystore_file_path.unlink()


class TokenSwapTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.rdn_amount = TokenAmount(75, self._get_RDN())

    def _ensure_ethereum_funds(self, ethereum_amount: EthereumAmount):
        w3 = self._get_web3()
        current_balance = self.account.get_ethereum_balance(w3)
        log.debug(f"Current balance: {current_balance.formatted}")
        network = self._get_network()

        if current_balance < ethereum_amount:
            needed_funds = EthereumAmount(Wei(ethereum_amount.as_wei - current_balance.as_wei))
            print(
                f"Please send at least {needed_funds.formatted} to {self.account.address} on "
                f"{network.capitalized_name}"
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
    @override_settings(network="ropsten")
    def test_swap(self):
        self._execute_rdn_swap(Kyber(w3=self.w3))


class UniswapExchangeRDNTestCase(TokenSwapTestCase):
    def setUp(self):
        super().setUp()
        self.uniswap = Uniswap(w3=self.w3)

    @override_settings(network="mainnet")
    def test_swap(self):
        self._execute_rdn_swap(self.uniswap)

    @override_settings(network="mainnet")
    def test_gas_estimate(self):
        costs = self.uniswap.calculate_transaction_costs(self.rdn_amount, self.account)
        print(costs["gas"])


class TokenNetworkTestCase(BaseTestCase):
    def _deposit(self):
        network = self._get_network()
        w3 = self._get_web3()
        ethereum_balance = self.account.get_ethereum_balance(w3=w3)

        log.debug(f"Ethereum Balance: {ethereum_balance.formatted}")
        if not ethereum_balance.as_wei:
            network.fund(self.account)

        token = Erc20Token.find_by_sticker(settings.service_token.sticker)
        token_balance = get_token_balance(w3, self.account, token)
        log.debug(f"Token Balance: {token_balance.formatted}")

        if not token_balance.as_wei:
            mint_tokens(w3, self.account, token)
            token_balance = get_token_balance(w3, self.account, token)
            log.debug(f"Tokens minted. New Balance: {token_balance.formatted}")

        deposit_service_tokens(w3, self.account, token, token_balance.as_wei)

    @override_settings(network="goerli")
    def test_goerli_deposit(self):
        self._deposit()

    @override_settings(network="ropsten")
    def test_ropsten_deposit(self):
        self._deposit()


# class UniswapExchangeSAITestCase(TokenSwapTestCase):
#     NETWORK_NAME = "rinkeby"

#     def test_swap(self):
#         log.debug(f"Making ETH <-> SAI swap for {self.account.address}")
#         self._ensure_ethereum_funds()
#         uniswap = Uniswap(w3=self.w3, account=self.account)
#         dai = uniswap.get_token("SAI")
#         log.debug(f"Before swap, balance is {dai.balance} SAI")
#         dai_exchange_rate = uniswap._get_exchange_rate("SAI", self.ethereum_amount)
#         uniswap._run_token_swap("SAI", self.ethereum_amount, dai_exchange_rate)
#         log.debug(f"After swap, balance is {dai.balance} SAI")

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

#         exchange_proxy = uniswap.get_exchange_proxy("SAI")
#         token_amount = exchange_proxy.functions.getEthToTokenInputPrice(
#             transaction_params["value"]
#         ).call()

#         transaction = exchange_proxy.functions.ethToTokenSwapInput(
#             token_amount, deadline
#         ).buildTransaction(transaction_params)
#         estimated_gas = self.w3.eth.estimateGas(transaction)

#         print(estimated_gas)


class ExchangeSelectionTestCase(TokenSwapTestCase):
    TOKEN_AMOUNTS = (50, 75, 100, 150, 200, 300, 500, 1000)

    def setUp(self):
        super().setUp()
        self.kyber = Kyber(w3=self.w3)
        self.uniswap = Uniswap(w3=self.w3)

    @override_settings(network="mainnet")
    def test_can_get_costs(self):
        print("\t".join([st.rjust(36) for st in ("RDN to buy", "Kyber", "Uniswap")]))

        for amount in self.TOKEN_AMOUNTS:
            rdn_amount = TokenAmount(amount, self._get_RDN())
            kyber_costs = self.kyber.calculate_transaction_costs(rdn_amount, self.account)
            uniswap_costs = self.uniswap.calculate_transaction_costs(rdn_amount, self.account)
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
