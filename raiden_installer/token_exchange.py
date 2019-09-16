from eth_utils import to_checksum_address
from ethtoken.abi import EIP20_ABI
from raiden_contracts.constants import CONTRACT_USER_DEPOSIT, CONTRACT_CUSTOM_TOKEN
from raiden_contracts.contract_manager import (
    ContractManager,
    contracts_precompiled_path,
    get_contracts_deployment_info,
)

from web3 import Web3

from . import log
from .account import Account
from .network import Network
from .kyber.web3 import tokens as kyber_tokens
from .kyber.web3 import contracts as kyber_contracts
from .uniswap.web3 import contracts as uniswap_contracts
from .typing import ETH_UNIT


def get_contract_address(chain_id, contract_name):
    return get_contracts_deployment_info(chain_id)["contracts"][contract_name]["address"]


def estimate_gas(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": int(w3.net.version),
        "nonce": w3.eth.getTransactionCount(to_checksum_address(account.address)),
        "gasPrice": kw.pop("gas_price", w3.eth.gasPrice),
    }
    transaction_params.update(**kw)
    result = contract_function(*args)
    transaction = result.buildTransaction(transaction_params)
    return w3.eth.estimateGas(transaction)


def send_raw_transaction(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": int(w3.net.version),
        "nonce": w3.eth.getTransactionCount(to_checksum_address(account.address)),
        "gasPrice": kw.pop("gas_price", w3.eth.gasPrice),
        "gas": kw.pop("gas", estimate_gas(w3, account, contract_function, *args, **kw)),
    }
    transaction_params.update(**kw)

    gas_price = transaction_params["gasPrice"]
    gas = transaction_params["gas"]
    value = transaction_params.get("value", 0)

    log.debug(f"Estimated cost: {(gas * gas_price) + value} WEI")

    result = contract_function(*args)
    transaction_data = result.buildTransaction(transaction_params)
    signed = w3.eth.account.signTransaction(transaction_data, account.private_key)
    tx_hash = w3.eth.sendRawTransaction(signed.rawTransaction)

    return w3.eth.waitForTransactionReceipt(tx_hash)


def eth_to_wei(eth_amount: ETH_UNIT) -> int:
    return int(eth_amount * (10 ** 18))


def wei_to_eth(wei_amount: int) -> ETH_UNIT:
    return ETH_UNIT(wei_amount / (10 ** 18))


class ExchangeError(Exception):
    pass


class Exchange:
    GAS_REQUIRED = 0

    SUPPORTED_NETWORKS = []

    def __init__(self, w3: Web3, account: Account):
        self.account = account
        self.w3 = w3
        self.w3.eth.defaultAccount = to_checksum_address(self.account.address)

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

    def get_current_rate(self, ethereum_amount: ETH_UNIT) -> ETH_UNIT:
        raise NotImplementedError

    def swap_ethereum_for_rdn(self, ethereum_amount: ETH_UNIT, exchange_rate: int):
        raise NotImplementedError

    @classmethod
    def select_by_rate(cls, w3: Web3, account: Account, ethereum_amount: ETH_UNIT):
        exchanges = [exchange_class(w3, account) for exchange_class in [Kyber, Uniswap]]
        rates = []
        for exchange in exchanges:
            try:
                rates.append(exchange.get_current_rate(ethereum_amount))
            except ExchangeError:
                pass
        return exchanges[rates.index(min(rates))]


class Kyber(Exchange):
    GAS_REQUIRED = 500_000

    SUPPORTED_NETWORKS = ["ropsten", "mainnet"]

    def __init__(self, w3: Web3, account: Account):
        super().__init__(w3=w3, account=account)
        self.network_contract_proxy = kyber_contracts.get_network_contract_proxy(self.w3)

    @property
    def rdn_token_network_address(self):
        return to_checksum_address(kyber_tokens.get_token_network_address(self.chain_id, "RDN"))

    def get_current_rate(self, ethereum_amount: ETH_UNIT) -> ETH_UNIT:
        wei_amount = eth_to_wei(ethereum_amount)
        eth_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, "ETH")
        )

        expected_rate, slippage_rate = self.network_contract_proxy.functions.getExpectedRate(
            eth_address, self.rdn_token_network_address, wei_amount
        ).call()

        if expected_rate == 0 or slippage_rate == 0:
            raise ExchangeError("Trade not possible at the moment due to lack of liquidity")

        return wei_to_eth(slippage_rate)

    def swap_ethereum_for_rdn(self, ethereum_amount: ETH_UNIT, exchange_rate: ETH_UNIT):
        if self.network.name not in self.SUPPORTED_NETWORKS:
            raise ExchangeError(f"Kyber does not list RDN on {self.network.name}")

        wei_to_sell = eth_to_wei(ethereum_amount)

        transaction_params = {
            "from": to_checksum_address(self.account.address),
            "value": wei_to_sell,
        }

        gas_price = min(
            self.w3.eth.gasPrice, self.network_contract_proxy.functions.maxGasPrice().call()
        )
        gas = estimate_gas(
            self.w3,
            self.account,
            self.network_contract_proxy.functions.swapEtherToToken,
            self.rdn_token_network_address,
            eth_to_wei(exchange_rate),
            **transaction_params,
        )

        wei_to_sell -= gas * gas_price

        transaction_params.update({"gas_price": gas_price, "gas": gas, "value": wei_to_sell})
        return send_raw_transaction(
            self.w3,
            self.account,
            self.network_contract_proxy.functions.swapEtherToToken,
            self.rdn_token_network_address,
            eth_to_wei(exchange_rate),
            **transaction_params,
        )


class Uniswap(Exchange):
    GAS_REQUIRED = 75_000
    RAIDEN_EXCHANGE_ADDRESSES = {"mainnet": "0x7D03CeCb36820b4666F45E1b4cA2538724Db271C"}
    DAI_EXCHANGE_ADDRESSES = {
        "kovan": "0x8779C708e2C3b1067de9Cd63698E4334866c691C",
        "rinkeby": "0x77dB9C915809e7BE439D2AB21032B1b8B58F6891",
    }
    EXCHANGE_FEE = 0.003
    EXCHANGE_TIMEOUT = 20 * 60  # maximum waiting time in seconds

    def _run_token_swap(
        self, token_sticker: str, ethereum_amount: ETH_UNIT, exchange_rate: ETH_UNIT
    ):
        try:
            exchange_proxy = self.get_exchange_proxy(token_sticker)
        except KeyError:
            raise ExchangeError(f"Uniswap does not list {token_sticker} on {self.network.name}")

        log.debug("Getting latest block info data")
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + self.EXCHANGE_TIMEOUT
        wei_amount = eth_to_wei(ethereum_amount)

        token_amount = self._get_tokens_available(token_sticker, ethereum_amount)
        transaction_params = {
            "from": self.w3.eth.defaultAccount,
            "value": wei_amount,
            "gas": self.GAS_REQUIRED,
        }
        return send_raw_transaction(
            self.w3,
            self.account,
            exchange_proxy.functions.ethToTokenSwapInput,
            token_amount,
            deadline,
            **transaction_params,
        )

    def get_exchange_proxy(self, token_sticker):
        return self.w3.eth.contract(
            abi=uniswap_contracts.UNISWAP_EXCHANGE_ABI,
            address=self._get_exchange_address(token_sticker),
        )

    def _get_tokens_available(self, token_sticker: str, ethereum_amount: ETH_UNIT) -> int:
        try:
            exchange_proxy = self.get_exchange_proxy(token_sticker)
        except KeyError:
            raise ExchangeError(f"Uniswap does not list {token_sticker} on {self.network.name}")

        wei_amount = eth_to_wei(ethereum_amount)
        return exchange_proxy.functions.getEthToTokenInputPrice(wei_amount).call()

    def _get_exchange_rate(self, token_sticker: str, ethereum_amount: ETH_UNIT):
        wei_amount = eth_to_wei(ethereum_amount)
        exchange_proxy = self.get_exchange_proxy(token_sticker)

        tokens_to_receive = wei_to_eth(
            exchange_proxy.functions.getEthToTokenInputPrice(wei_amount).call()
        )
        return ETH_UNIT(tokens_to_receive / ethereum_amount)

    def _get_exchange_address(self, token_sticker: str) -> str:
        try:
            exchanges = {"RDN": self.RAIDEN_EXCHANGE_ADDRESSES, "DAI": self.DAI_EXCHANGE_ADDRESSES}
            return exchanges[token_sticker][self.network.name]
        except KeyError:
            raise ExchangeError(f"{self.name} does not have a listed exchange for {token_sticker}")

    def _get_token_class(self, token_sticker: str):
        return {"RDN": RaidenToken, "DAI": DAIToken}[token_sticker]

    def get_token(self, token_sticker: str):
        return self._get_token_class(token_sticker)(w3=self.w3, account=self.account)

    def get_current_rate(self, ethereum_amount: ETH_UNIT) -> ETH_UNIT:
        return self._get_exchange_rate("RDN", ethereum_amount)

    def swap_ethereum_for_rdn(self, ethereum_amount: ETH_UNIT, exchange_rate: ETH_UNIT):
        return self._run_token_swap("RDN", ethereum_amount, exchange_rate)


class Token:
    NETWORKS_DEPLOYED = []

    def __init__(self, w3: Web3, account: Account):
        self.account = account
        self.w3 = w3
        self.w3.eth.defaultAccount = self.owner
        network = Network.get_by_chain_id(int(w3.net.version))
        if self.is_available(network):
            self.token_network_address = self._get_token_network_address()
            self.token_proxy = self._get_token_proxy()

    @property
    def owner(self):
        return to_checksum_address(self.account.address)

    @property
    def balance(self):
        return wei_to_eth(self.token_proxy.functions.balanceOf(self.owner).call())

    @property
    def is_funded(self):
        return self.balance > 0

    def is_available(self, network: Network):
        return network.name in self.NETWORKS_DEPLOYED

    def _get_token_proxy(self):
        return self.w3.eth.contract(address=self.token_network_address, abi=EIP20_ABI)

    def _get_token_network_address(self):
        raise NotImplementedError


class CustomToken(Token):
    TOKEN_AMOUNT = 10 ** 21
    GAS_REQUIRED_FOR_MINT = 100_000
    GAS_REQUIRED_FOR_DEPOSIT = 200_000
    GAS_REQUIRED_FOR_APPROVE = 70_000

    NETWORKS_DEPLOYED = ["goerli"]

    def _get_token_network_address(self):
        deposit_proxy = self._get_deposit_proxy()
        return deposit_proxy.functions.token().call()

    def _get_deposit_proxy(self):
        contract_manager = ContractManager(contracts_precompiled_path())
        contract_address = get_contract_address(int(self.w3.net.version), CONTRACT_USER_DEPOSIT)
        return self.w3.eth.contract(
            address=contract_address, abi=contract_manager.get_contract_abi(CONTRACT_USER_DEPOSIT)
        )

    def _get_token_proxy(self):
        contract_manager = ContractManager(contracts_precompiled_path())
        return self.w3.eth.contract(
            address=self.token_network_address,
            abi=contract_manager.get_contract_abi(CONTRACT_CUSTOM_TOKEN),
        )

    def mint(self, amount: int):
        return send_raw_transaction(
            self.w3,
            self.account,
            self.token_proxy.functions.mint,
            amount,
            gas=self.GAS_REQUIRED_FOR_MINT,
        )

    def deposit(self, amount: int):

        deposit_proxy = self._get_deposit_proxy()

        send_raw_transaction(
            self.w3,
            self.account,
            self.token_proxy.functions.approve,
            deposit_proxy.address,
            amount,
            gas=self.GAS_REQUIRED_FOR_APPROVE,
        )

        return send_raw_transaction(
            self.w3,
            self.account,
            deposit_proxy.functions.deposit,
            self.owner,
            amount,
            gas=self.GAS_REQUIRED_FOR_DEPOSIT,
        )


class DAIToken(Token):
    NETWORKS_DEPLOYED = ["mainnet", "ropsten", "rinkeby", "kovan"]

    def _get_token_network_address(self):
        network = Network.get_by_chain_id(int(self.w3.net.version))
        address = {
            "mainnet": "0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359",
            "ropsten": "0xaD6D458402F60fD3Bd25163575031ACDce07538D",
            "rinkeby": "0x2448eE2641d78CC42D7AD76498917359D961A783",
            "kovan": "0xc4375b7de8af5a38a93548eb8453a498222c4ff2",
        }[network.name]

        return to_checksum_address(address)


class RaidenToken(Token):
    NETWORKS_DEPLOYED = ["mainnet", "ropsten", "rinkeby", "kovan"]

    def _get_token_network_address(self):
        network = Network.get_by_chain_id(int(self.w3.net.version))
        address = {
            "mainnet": "0x255aa6df07540cb5d3d297f0d0d4d84cb52bc8e6",
            "ropsten": "0x5422Ef695ED0B1213e2B953CFA877029637D9D26",
            "rinkeby": "0x51892e7e4085df269de688b273209f3969f547e0",
            "kovan": "0x3a03155696708f517c53ffc4f696dfbfa7743795",
        }[network.name]

        return to_checksum_address(address)
