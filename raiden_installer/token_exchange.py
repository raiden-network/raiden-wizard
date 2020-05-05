from decimal import Decimal
from typing import List, Optional

import structlog
from eth_utils import to_checksum_address
from web3 import Web3

from raiden_installer.account import Account
from raiden_installer.kyber.web3 import contracts as kyber_contracts, tokens as kyber_tokens
from raiden_installer.network import Network
from raiden_installer.tokens import EthereumAmount, TokenAmount, TokenTicker, Wei
from raiden_installer.uniswap.web3 import contracts as uniswap_contracts
from raiden_installer.utils import estimate_gas, send_raw_transaction

log = structlog.get_logger()


class ExchangeError(Exception):
    pass


class Exchange:
    GAS_REQUIRED = 0
    SUPPORTED_NETWORKS: List[str] = []
    TRANSFER_WEBSITE_URL: Optional[str] = None
    MAIN_WEBSITE_URL: Optional[str] = None
    TERMS_OF_SERVICE_URL: Optional[str] = None
    GAS_PRICE_MARGIN = 1.25

    def __init__(self, w3: Web3):
        self.w3 = w3

    @property
    def chain_id(self):
        return int(self.w3.net.version)

    @property
    def network(self):
        return Network.get_by_chain_id(self.chain_id)

    @property
    def is_mainnet(self):
        return self.network.name == "mainnet"

    @property
    def name(self):
        return self.__class__.__name__

    def get_current_rate(self, token_amount: TokenAmount) -> EthereumAmount:
        raise NotImplementedError

    def calculate_transaction_costs(
        self, token_amount: TokenAmount, account: Account
    ) -> Optional[dict]:
        if not self.is_listing_token(token_amount.ticker) or token_amount.as_wei <= 0:
            return None

        return self._calculate_transaction_costs(token_amount, account)

    def _calculate_transaction_costs(self, token_amount: TokenAmount, account: Account) -> dict:
        raise NotImplementedError

    def buy_tokens(self, account: Account, token_amount: TokenAmount, transaction_costs=dict()):
        raise NotImplementedError

    def is_listing_token(self, ticker: TokenTicker):
        return False

    @classmethod
    def get_by_name(cls, name):
        return {"kyber": Kyber, "uniswap": Uniswap}[name.lower()]


class Kyber(Exchange):
    GAS_REQUIRED = 500_000
    SUPPORTED_NETWORKS = ["ropsten", "mainnet"]
    MAIN_WEBSITE_URL = "https://kyber.network"
    TRANSFER_WEBSITE_URL = "https://kyberswap.com/transfer/eth"
    TERMS_OF_SERVICE_URL = "https://kyber.network/terms-and-conditions"

    def __init__(self, w3: Web3):
        super().__init__(w3=w3)
        self.network_contract_proxy = kyber_contracts.get_network_contract_proxy(self.w3)

    def is_listing_token(self, ticker: TokenTicker):
        token_network_address = self.get_token_network_address(ticker)
        return token_network_address is not None

    def get_token_network_address(self, ticker: TokenTicker):
        try:
            token_network_address = kyber_tokens.get_token_network_address(self.chain_id, ticker)
            return token_network_address and to_checksum_address(token_network_address)
        except KeyError:
            return None

    def get_current_rate(self, token_amount: TokenAmount) -> EthereumAmount:
        eth_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, TokenTicker("ETH"))
        )

        token_network_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, token_amount.ticker)
        )

        expected_rate, slippage_rate = self.network_contract_proxy.functions.getExpectedRate(
            token_network_address, eth_address, token_amount.as_wei
        ).call()

        if expected_rate == 0 or slippage_rate == 0:
            raise ExchangeError("Trade not possible at the moment due to lack of liquidity")

        return EthereumAmount(Wei(max(expected_rate, slippage_rate)))

    def _calculate_transaction_costs(self, token_amount: TokenAmount, account: Account) -> dict:
        exchange_rate = self.get_current_rate(token_amount)
        eth_sold = EthereumAmount(token_amount.value * exchange_rate.value * Decimal(1.2))
        web3_gas_price = Wei(int(self.w3.eth.generateGasPrice() * self.GAS_PRICE_MARGIN))

        kyber_max_gas_price = self.network_contract_proxy.functions.maxGasPrice().call()
        max_gas_price = min(web3_gas_price, kyber_max_gas_price)
        gas_price = EthereumAmount(Wei(max_gas_price))
        log.debug(f"gas price: {gas_price}")
        token_network_address = self.get_token_network_address(token_amount.ticker)
        transaction_params = {"from": account.address, "value": eth_sold.as_wei}
        eth_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, TokenTicker("ETH"))
        )

        gas = estimate_gas(
            self.w3,
            account,
            self.network_contract_proxy.functions.trade,
            eth_address,
            eth_sold.as_wei,
            token_network_address,
            account.address,
            token_amount.as_wei,
            exchange_rate.as_wei,
            account.address,
            **transaction_params,
        )

        block = self.w3.eth.getBlock(self.w3.eth.blockNumber)
        max_gas_limit = Wei(int(block["gasLimit"] * 0.9))
        gas_with_margin = Wei(int(gas * self.GAS_PRICE_MARGIN))
        gas = max(gas_with_margin, max_gas_limit)

        if max_gas_limit < gas_with_margin:
            log.debug(
                f"calculated gas was higher than block's gas limit {max_gas_limit}. Using this limit."
            )

        gas_cost = EthereumAmount(Wei(gas * gas_price.as_wei))
        total = EthereumAmount(gas_cost.value + eth_sold.value)

        log.debug("transaction cost", gas_price=gas_price, gas=gas, eth=eth_sold)

        return {
            "gas_price": gas_price,
            "gas": gas,
            "eth_sold": eth_sold,
            "total": total,
            "exchange_rate": exchange_rate,
        }

    def buy_tokens(self, account: Account, token_amount: TokenAmount, transaction_costs=dict()):
        if self.network.name not in self.SUPPORTED_NETWORKS:
            raise ExchangeError(
                f"{self.name} does not list {token_amount.ticker} on {self.network.name}"
            )

        if not transaction_costs:
            transaction_costs = self.calculate_transaction_costs(token_amount, account)
        if transaction_costs is None:
            raise ExchangeError("Failed to get transactions costs")

        eth_to_sell = transaction_costs["eth_sold"]
        exchange_rate = transaction_costs["exchange_rate"]
        gas_price = transaction_costs["gas_price"]
        gas = transaction_costs["gas"]

        eth_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, TokenTicker("ETH"))
        )

        transaction_params = {
            "from": account.address,
            "gas_price": gas_price.as_wei,
            "gas": gas,
            "value": eth_to_sell.as_wei,
        }
        return send_raw_transaction(
            self.w3,
            account,
            self.network_contract_proxy.functions.trade,
            eth_address,
            eth_to_sell.as_wei,
            self.get_token_network_address(token_amount.ticker),
            account.address,
            token_amount.as_wei,
            exchange_rate.as_wei,
            account.address,
            **transaction_params,
        )


class Uniswap(Exchange):
    GAS_REQUIRED = 75_000
    RAIDEN_EXCHANGE_ADDRESSES = {"mainnet": "0x7D03CeCb36820b4666F45E1b4cA2538724Db271C"}
    DAI_EXCHANGE_ADDRESSES = {"mainnet": "0x2a1530C4C41db0B0b2bB646CB5Eb1A67b7158667"}
    EXCHANGE_FEE = 0.003
    EXCHANGE_TIMEOUT = 20 * 60  # maximum waiting time in seconds
    TRANSFER_WEBSITE_URL = "https://uniswap.ninja/send"
    MAIN_WEBSITE_URL = "https://uniswap.io"
    TERMS_OF_SERVICE_URL = "https://uniswap.io"

    def _get_exchange_proxy(self, token_ticker):
        try:
            return self.w3.eth.contract(
                abi=uniswap_contracts.UNISWAP_EXCHANGE_ABI,
                address=self._get_exchange_address(token_ticker),
            )
        except ExchangeError:
            return None

    def is_listing_token(self, ticker: TokenTicker):
        try:
            self._get_exchange_address(ticker)
            return True
        except ExchangeError:
            return False

    def _get_exchange_address(self, token_ticker: TokenTicker) -> str:
        try:
            exchanges = {"RDN": self.RAIDEN_EXCHANGE_ADDRESSES, "DAI": self.DAI_EXCHANGE_ADDRESSES}
            return exchanges[token_ticker][self.network.name]
        except KeyError:
            raise ExchangeError(f"{self.name} does not have a listed exchange for {token_ticker}")

    def _calculate_transaction_costs(self, token_amount: TokenAmount, account: Account) -> dict:
        exchange_rate = self.get_current_rate(token_amount)
        eth_sold = EthereumAmount(token_amount.value * exchange_rate.value)
        gas_price = EthereumAmount(
            Wei(int(self.w3.eth.generateGasPrice() * self.GAS_PRICE_MARGIN))
        )
        exchange_proxy = self._get_exchange_proxy(token_amount.ticker)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + self.EXCHANGE_TIMEOUT
        transaction_params = {"from": account.address, "value": eth_sold.as_wei}

        gas = estimate_gas(
            self.w3,
            account,
            exchange_proxy.functions.ethToTokenSwapOutput,
            token_amount.as_wei,
            deadline,
            **transaction_params,
        )

        block = self.w3.eth.getBlock(self.w3.eth.blockNumber)
        max_gas_limit = int(block["gasLimit"] * 0.9)

        gas = max(Wei(int(gas * self.GAS_PRICE_MARGIN)), max_gas_limit)

        gas_cost = EthereumAmount(Wei(gas * gas_price.as_wei))
        total = EthereumAmount(gas_cost.value + eth_sold.value)
        return {
            "gas_price": gas_price,
            "gas": gas,
            "eth_sold": eth_sold,
            "total": total,
            "exchange_rate": exchange_rate,
        }

    def buy_tokens(self, account: Account, token_amount: TokenAmount, transaction_costs=dict()):
        if transaction_costs:
            costs = transaction_costs
        else:
            costs = self.calculate_transaction_costs(token_amount, account)



        if costs is None:
            raise ExchangeError("Failed to get transaction costs")

        exchange_proxy = self._get_exchange_proxy(token_amount.ticker)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + self.EXCHANGE_TIMEOUT
        gas = costs["gas"]
        gas_price = costs["gas_price"]
        transaction_params = {
            "from": account.address,
            "value": costs["total"].as_wei,
            "gas": 2 * gas,  # estimated gas sometimes is not enough
            "gas_price": gas_price.as_wei,
        }

        return send_raw_transaction(
            self.w3,
            account,
            exchange_proxy.functions.ethToTokenSwapOutput,
            token_amount.as_wei,
            deadline,
            **transaction_params,
        )

    def get_current_rate(self, token_amount: TokenAmount) -> EthereumAmount:
        exchange_proxy = self._get_exchange_proxy(token_amount.ticker)

        eth_to_sell = EthereumAmount(
            Wei(exchange_proxy.functions.getEthToTokenOutputPrice(token_amount.as_wei).call())
        )
        return EthereumAmount(eth_to_sell.value / token_amount.value)
