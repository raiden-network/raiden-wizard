import unittest

from raiden_installer.tokens import Erc20Token, EthereumAmount, TokenAmount, Wei


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
