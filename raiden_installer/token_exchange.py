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
from .tokens import (
    Wei,
    TokenAmount,
    EthereumAmount,
    TokenSticker,
    RDNAmount,
    DAIAmount,
    GoerliRaidenAmount,
)


def get_contract_address(chain_id, contract_name):
    return get_contracts_deployment_info(chain_id)["contracts"][contract_name]["address"]


def estimate_gas(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": int(w3.net.version),
        "nonce": w3.eth.getTransactionCount(to_checksum_address(account.address)),
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

    estimated_cost = EthereumAmount(Wei((gas * gas_price) + value))

    log.debug(f"Estimated cost: {estimated_cost.formatted}")

    result = contract_function(*args)
    transaction_data = result.buildTransaction(transaction_params)
    signed = w3.eth.account.signTransaction(transaction_data, account.private_key)
    tx_hash = w3.eth.sendRawTransaction(signed.rawTransaction)

    return w3.eth.waitForTransactionReceipt(tx_hash)


class ExchangeError(Exception):
    pass


class Exchange:
    GAS_REQUIRED = 0

    SUPPORTED_NETWORKS = []

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

    def _get_token_class(self, token_sticker: TokenSticker):
        return {"RDN": RaidenTokenNetwork, "DAI": DAITokenNetwork}[token_sticker]

    def get_token(self, token_sticker: TokenSticker):
        return self._get_token_class(token_sticker)(w3=self.w3)

    def get_current_rate(self, token_amount: TokenAmount) -> EthereumAmount:
        raise NotImplementedError

    def calculate_transaction_costs(self, token_amount: TokenAmount, account: Account) -> dict:
        raise NotImplementedError

    def buy_tokens(self, account: Account, token_amount: TokenAmount):
        raise NotImplementedError

    def is_listing_token(self, sticker: TokenSticker):
        return False

    @classmethod
    def get_by_name(cls, name):
        return {"kyber": Kyber, "uniswap": Uniswap}[name.lower()]


class Kyber(Exchange):
    GAS_REQUIRED = 500_000

    SUPPORTED_NETWORKS = ["ropsten", "mainnet"]

    def __init__(self, w3: Web3):
        super().__init__(w3=w3)
        self.network_contract_proxy = kyber_contracts.get_network_contract_proxy(self.w3)

    def is_listing_token(self, sticker: TokenSticker):
        try:
            self.get_token_network_address(sticker)
            return True
        except (KeyError, ExchangeError):
            return False

    def get_token_network_address(self, sticker: TokenSticker):
        return to_checksum_address(kyber_tokens.get_token_network_address(self.chain_id, sticker))

    def get_current_rate(self, token_amount: TokenAmount) -> EthereumAmount:
        eth_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, TokenSticker("ETH"))
        )

        token_network_address = to_checksum_address(
            kyber_tokens.get_token_network_address(self.chain_id, token_amount.sticker)
        )

        expected_rate, slippage_rate = self.network_contract_proxy.functions.getExpectedRate(
            token_network_address, eth_address, token_amount.as_wei
        ).call()

        if expected_rate == 0 or slippage_rate == 0:
            raise ExchangeError("Trade not possible at the moment due to lack of liquidity")

        return EthereumAmount(Wei(slippage_rate))

    def calculate_transaction_costs(self, token_amount: TokenAmount, account: Account) -> dict:
        exchange_rate = self.get_current_rate(token_amount)
        eth_sold = EthereumAmount(token_amount.value * exchange_rate.value)
        max_gas_price = min(
            self.w3.eth.gasPrice, self.network_contract_proxy.functions.maxGasPrice().call()
        )
        gas_price = EthereumAmount(Wei(max_gas_price))
        token_network_address = self.get_token_network_address(token_amount.sticker)
        transaction_params = {
            "from": to_checksum_address(account.address),
            "value": eth_sold.as_wei,
        }

        gas = estimate_gas(
            self.w3,
            account,
            self.network_contract_proxy.functions.swapEtherToToken,
            token_network_address,
            exchange_rate.as_wei,
            **transaction_params,
        )

        gas_cost = EthereumAmount(Wei(gas * gas_price.as_wei))
        total = EthereumAmount(gas_cost.value + eth_sold.value)
        return {
            "gas_price": gas_price,
            "gas": gas,
            "eth_sold": eth_sold,
            "total": total,
            "exchange_rate": exchange_rate,
        }

    def buy_tokens(self, account: Account, token_amount: TokenAmount):
        if self.network.name not in self.SUPPORTED_NETWORKS:
            raise ExchangeError(
                f"{self.name} does not list {token_amount.sticker} on {self.network.name}"
            )

        transaction_costs = self.calculate_transaction_costs(token_amount)
        eth_to_sell = transaction_costs["eth_sold"]
        exchange_rate = transaction_costs["exchange_rate"]
        gas_price = transaction_costs["gas_price"]
        gas = transaction_costs["gas"]

        transaction_params = {
            "from": to_checksum_address(account.address),
            "gas_price": gas_price.as_wei,
            "gas": gas,
            "value": eth_to_sell.as_wei,
        }

        return send_raw_transaction(
            self.w3,
            account,
            self.network_contract_proxy.functions.swapEtherToToken,
            self.get_token_network_address(token_amount.sticker),
            exchange_rate.as_wei,
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

    def get_exchange_proxy(self, token_sticker):
        return self.w3.eth.contract(
            abi=uniswap_contracts.UNISWAP_EXCHANGE_ABI,
            address=self._get_exchange_address(token_sticker),
        )

    def is_listing_token(self, sticker: TokenSticker):
        try:
            self._get_exchange_address(sticker)
            return True
        except ExchangeError:
            return False

    def _get_exchange_address(self, token_sticker: TokenSticker) -> str:
        try:
            exchanges = {"RDN": self.RAIDEN_EXCHANGE_ADDRESSES, "DAI": self.DAI_EXCHANGE_ADDRESSES}
            return exchanges[token_sticker][self.network.name]
        except KeyError:
            raise ExchangeError(f"{self.name} does not have a listed exchange for {token_sticker}")

    def calculate_transaction_costs(self, account: Account, token_amount: TokenAmount) -> dict:
        exchange_rate = self.get_current_rate(token_amount)
        eth_to_sell = EthereumAmount(token_amount.value * exchange_rate.value)
        gas_price = EthereumAmount(Wei(self.w3.eth.gasPrice))
        exchange_proxy = self.get_exchange_proxy(token_amount.sticker)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + self.EXCHANGE_TIMEOUT
        transaction_params = {"from": account.checksum_address, "value": eth_to_sell.as_wei}

        gas = estimate_gas(
            self.w3,
            account,
            exchange_proxy.functions.ethToTokenSwapOutput,
            token_amount.as_wei,
            deadline,
            **transaction_params,
        )

        gas_cost = EthereumAmount(Wei(gas * gas_price.as_wei))
        total = EthereumAmount(gas_cost.value + eth_to_sell.value)
        return {
            "gas_price": gas_price,
            "gas": gas,
            "eth_to_sell": eth_to_sell,
            "total": total,
            "exchange_rate": exchange_rate,
        }

    def buy_tokens(self, account: Account, token_amount: TokenAmount):
        costs = self.calculate_transaction_costs(token_amount)
        exchange_proxy = self.get_exchange_proxy(token_amount.sticker)
        latest_block = self.w3.eth.getBlock("latest")
        deadline = latest_block.timestamp + self.EXCHANGE_TIMEOUT
        eth_to_sell = costs["eth_to_sell"]
        gas = costs["gas"]
        gas_price = costs["gas_price"]
        transaction_params = {
            "from": account.checksum_address,
            "value": eth_to_sell.as_wei,
            "gas": gas,
            "gas_price": gas_price,
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
        exchange_proxy = self.get_exchange_proxy(token_amount.sticker)

        eth_to_sell = EthereumAmount(
            Wei(exchange_proxy.functions.getEthToTokenOutputPrice(token_amount.as_wei).call())
        )
        return EthereumAmount(eth_to_sell.value / token_amount.value)


class TokenNetwork:
    NETWORKS_DEPLOYED = []
    TOKEN_AMOUNT_CLASS = None

    def __init__(self, w3: Web3):
        self.w3 = w3
        network = Network.get_by_chain_id(int(w3.net.version))
        if self.is_available(network):
            self.token_network_address = self._get_token_network_address()
            self.token_proxy = self._get_token_proxy()

    def balance(self, account: Account) -> TokenAmount:
        assert self.TOKEN_AMOUNT_CLASS is not None

        return self.TOKEN_AMOUNT_CLASS(
            Wei(self.token_proxy.functions.balanceOf(account.checksum_address).call())
        )

    def is_available(self, network: Network):
        return network.name in self.NETWORKS_DEPLOYED

    def _get_token_proxy(self):
        return self.w3.eth.contract(address=self.token_network_address, abi=EIP20_ABI)

    def _get_token_network_address(self):
        raise NotImplementedError


class CustomTokenNetwork(TokenNetwork):
    TOKEN_AMOUNT_CLASS = GoerliRaidenAmount
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

    def mint(self, account: Account, amount: int):
        return send_raw_transaction(
            self.w3,
            account,
            self.token_proxy.functions.mint,
            amount,
            gas=self.GAS_REQUIRED_FOR_MINT,
        )

    def deposit(self, account: Account, amount: int):

        deposit_proxy = self._get_deposit_proxy()

        send_raw_transaction(
            self.w3,
            account,
            self.token_proxy.functions.approve,
            deposit_proxy.address,
            amount,
            gas=self.GAS_REQUIRED_FOR_APPROVE,
        )

        return send_raw_transaction(
            self.w3,
            account,
            deposit_proxy.functions.deposit,
            account.checksum_address,
            amount,
            gas=self.GAS_REQUIRED_FOR_DEPOSIT,
        )


class DAITokenNetwork(TokenNetwork):
    NETWORKS_DEPLOYED = ["mainnet", "ropsten", "rinkeby", "kovan"]
    TOKEN_AMOUNT_CLASS = DAIAmount

    def _get_token_network_address(self):
        network = Network.get_by_chain_id(int(self.w3.net.version))
        address = {
            "mainnet": "0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359",
            "ropsten": "0xaD6D458402F60fD3Bd25163575031ACDce07538D",
            "rinkeby": "0x2448eE2641d78CC42D7AD76498917359D961A783",
            "kovan": "0xc4375b7de8af5a38a93548eb8453a498222c4ff2",
        }[network.name]

        return to_checksum_address(address)


class RaidenTokenNetwork(TokenNetwork):
    TOKEN_AMOUNT_CLASS = RDNAmount
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
