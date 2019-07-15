import os
import unittest
import tempfile
from pathlib import Path

from installer import base


ETHEREUM_RPC_ENDPOINT = os.getenv("TEST_RAIDEN_INSTALLER_ETH_RPC_URL")
ETHEREUM_NETWORK_NAME = os.getenv("TEST_RAIDEN_INSTALLER_ETHEREUM_NETWORK")


@unittest.skipIf(
    ETHEREUM_RPC_ENDPOINT is None or ETHEREUM_NETWORK_NAME is None,
    "missing configuration for ethereum rpc url and/or network",
)
class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        base.Account.DEFAULT_KEYSTORE_FOLDER = Path(tempfile.gettempdir()).joinpath(
            "raiden", "installer", "integration"
        )
        self.ethereum_rpc_provider = base.EthereumRPCProvider.make_from_url(
            ETHEREUM_RPC_ENDPOINT
        )
        self.account = base.Account.create("test_raiden_integration")
        self.network = base.Network.get_by_name(ETHEREUM_NETWORK_NAME)

    def tearDown(self):
        base.Account.DEFAULT_KEYSTORE_FOLDER.unlink()


class NetworkTestCase(IntegrationTestCase):
    def test_can_fund_account(self):
        self.network.fund(self.account)
        self.assertTrue(self.account.balance > 0)


class TokenTestCase(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.token = base.Token(
            ethereum_rpc_endppoint=ETHEREUM_RPC_ENDPOINT, account=self.account
        )

    def test_can_not_mint_tokens_without_gas(self):
        with self.assertRaises(ValueError):
            self.token.mint(self.token.TOKEN_AMOUNT)

    def test_can_mint_tokens(self):
        self.network.fund(self.account)

        self.token.mint(self.token.TOKEN_AMOUNT)
