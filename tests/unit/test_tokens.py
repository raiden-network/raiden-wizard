import unittest

from raiden_installer import load_settings
from raiden_installer.tokens import (
    Erc20Token,
    EthereumAmount,
    RequiredAmounts,
    SwapAmounts,
    TokenAmount,
    TokenError,
    Wei,
)


class TokenAmountTestCase(unittest.TestCase):
    def setUp(self):
        self.one_eth = EthereumAmount(1)
        self.two_eth = EthereumAmount(2)
        self.one_rdn = TokenAmount(1, Erc20Token.find_by_ticker("RDN", "mainnet"))
        self.one_wiz = TokenAmount(1, Erc20Token.find_by_ticker("WIZ", "goerli"))

    def test_can_convert_to_wei(self):
        self.assertEqual(self.one_eth.as_wei, Wei(10 ** 18))

    def test_can_multiply_amounts(self):
        two_eth_in_wei = 2 * self.one_eth.as_wei

        self.assertEqual(two_eth_in_wei, Wei(2 * 10 ** 18))

    def test_can_get_token_ticker(self):
        self.assertEqual(self.one_rdn.ticker, "RDN")

    def test_can_get_formatted_amount(self):
        zero_eth = EthereumAmount(0)
        one_twei = EthereumAmount(Wei(10 ** 12))
        one_gwei = EthereumAmount(Wei(10 ** 9))
        one_mwei = EthereumAmount(Wei(10 ** 6))
        almost_one_eth = EthereumAmount("0.875")
        some_wei = EthereumAmount(Wei(50_000))

        self.assertEqual(self.one_eth.formatted, "1 ETH")
        self.assertEqual(self.one_rdn.formatted, "1 RDN")
        self.assertEqual(zero_eth.formatted, "0 ETH")
        self.assertEqual(one_twei.formatted, "1 TWEI")
        self.assertEqual(one_gwei.formatted, "1 GWEI")
        self.assertEqual(one_mwei.formatted, "1 MWEI")
        self.assertEqual(almost_one_eth.formatted, "0.875 ETH")
        self.assertEqual(some_wei.formatted, "50000 WEI")

    def test_addition(self):
        added_eth = self.one_eth + self.two_eth
        self.assertEqual(added_eth.value, 3)

    def test_cannot_add_different_currencies(self):
        with self.assertRaises(ValueError):
            self.one_rdn + self.one_wiz

    def test_subtraction(self):
        subtracted_eth = self.two_eth - self.one_eth
        self.assertEqual(subtracted_eth.value, 1)

    def test_cannot_subtract_different_currencies(self):
        with self.assertRaises(ValueError):
            self.one_rdn - self.one_wiz

    def test_equality(self):
        self.assertEqual(self.one_eth, EthereumAmount(1))

    def test_lt_operator(self):
        self.assertLess(self.one_eth, self.two_eth)

    def test_cannot_compare_different_currencies_with_lt_operator(self):
        with self.assertRaises(ValueError):
            self.one_rdn < self.one_wiz

    def test_le_operator(self):
        self.assertLessEqual(self.one_eth, EthereumAmount(1))

    def test_cannot_compare_different_currencies_with_le_operator(self):
        with self.assertRaises(ValueError):
            self.one_rdn <= self.one_wiz

    def test_gt_operator(self):
        self.assertGreater(self.two_eth, self.one_eth)

    def test_cannot_compare_different_currencies_with_gt_operator(self):
        with self.assertRaises(ValueError):
            self.one_rdn > self.one_wiz

    def test_ge_operator(self):
        self.assertGreaterEqual(self.one_eth, EthereumAmount(1))

    def test_cannot_compare_different_currencies_with_ge_operator(self):
        with self.assertRaises(ValueError):
            self.one_rdn >= self.one_wiz

    def test_can_get_address(self):
        rdn_token = Erc20Token.find_by_ticker("RDN", "mainnet")
        self.assertEqual(self.one_rdn.address, rdn_token.address)


class Erc20TokenTestCase(unittest.TestCase):
    def test_cannot_get_address_when_no_network_set(self):
        rdn_token = Erc20Token.find_by_ticker("RDN")
        with self.assertRaises(TokenError):
            rdn_token.address

    def test_cannot_get_address_on_network_without_deployment(self):
        rdn_token = Erc20Token.find_by_ticker("WIZ", "mainnet")
        with self.assertRaises(TokenError):
            rdn_token.address

    def test_get_address(self):
        rdn_token = Erc20Token.find_by_ticker("WIZ", "goerli")
        self.assertEqual(rdn_token.address, "0x95b2d84de40a0121061b105e6b54016a49621b44")


class InstallerAmountsTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings("mainnet")
        self.service_token = Erc20Token.find_by_ticker(
            self.settings.service_token.ticker,
            self.settings.network
        )
        self.transfer_token = Erc20Token.find_by_ticker(
            self.settings.transfer_token.ticker,
            self.settings.network
        )

    def test_create_required_amounts(self):
        required_amounts = RequiredAmounts.from_settings(self.settings)

        self.assertEqual(
            required_amounts.eth,
            EthereumAmount(Wei(self.settings.ethereum_amount_required))
        )
        self.assertEqual(
            required_amounts.eth_after_swap,
            EthereumAmount(Wei(self.settings.ethereum_amount_required_after_swap))
        )
        self.assertEqual(
            required_amounts.service_token,
            TokenAmount(Wei(self.settings.service_token.amount_required), self.service_token)
        )
        self.assertEqual(
            required_amounts.transfer_token,
            TokenAmount(Wei(self.settings.transfer_token.amount_required), self.transfer_token)
        )

    def test_create_swap_amounts(self):
        swap_amounts = SwapAmounts.from_settings(self.settings)

        self.assertEqual(
            swap_amounts.service_token,
            TokenAmount(Wei(self.settings.service_token.swap_amount), self.service_token)
        )
        self.assertEqual(
            swap_amounts.transfer_token,
            TokenAmount(Wei(self.settings.transfer_token.swap_amount), self.transfer_token)
        )
