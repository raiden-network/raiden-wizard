import os
import time

import pytest
from tests.constants import TESTING_KEYSTORE_FOLDER
from tests.fixtures import create_account, test_account, test_password
from tests.utils import empty_account

from raiden_installer.constants import WEB3_TIMEOUT
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.token_exchange import ExchangeError, Uniswap
from raiden_installer.tokens import Erc20Token, EthereumAmount, TokenAmount
from raiden_installer.transactions import approve, get_token_balance, mint_tokens
from raiden_installer.uniswap.web3 import contracts as uniswap_contracts
from raiden_installer.utils import send_raw_transaction, wait_for_transaction

INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")

NETWORK = Network.get_by_name("goerli")
WIZ_TOKEN = Erc20Token.find_by_ticker("WIZ", NETWORK.name)
GAS_LIMIT = 120_000


pytestmark = pytest.mark.skipif(not INFURA_PROJECT_ID, reason="missing configuration for infura")


def fund_account(account, w3):
    NETWORK.fund(account)
    account.wait_for_ethereum_funds(w3, EthereumAmount(0.01))


def generateDeadline(w3):
    current_timestamp = w3.eth.getBlock('latest')['timestamp']
    return current_timestamp + WEB3_TIMEOUT


def addLiquidity(w3, account, router_proxy, current_rate):
    max_tokens = get_token_balance(w3, account, WIZ_TOKEN)

    approve(w3, account, router_proxy.address, max_tokens.as_wei, WIZ_TOKEN)

    deadline = generateDeadline(w3)
    eth_amount = EthereumAmount(0.001)
    token_amount_desired = TokenAmount(eth_amount.value / current_rate.value, WIZ_TOKEN)
    transaction_params = {
        "from": account.address,
        "value": eth_amount.as_wei,
        "gas_price": w3.eth.generateGasPrice(),
        "gas": GAS_LIMIT,
    }

    tx_hash = send_raw_transaction(
        w3,
        account,
        router_proxy.functions.addLiquidityETH,
        WIZ_TOKEN.address,
        token_amount_desired.as_wei,
        int(token_amount_desired.as_wei * 0.8),
        int(eth_amount.as_wei * 0.8),
        account.address,
        deadline,
        **transaction_params,
    )
    wait_for_transaction(w3, tx_hash)


def get_pair_address(w3, router_proxy):
    weth_address = router_proxy.functions.WETH().call()
    factory_address = router_proxy.functions.factory().call()
    factory_proxy = w3.eth.contract(
        abi=uniswap_contracts.UNISWAP_FACTORY_ABI,
        address=factory_address,
    )
    return factory_proxy.functions.getPair(weth_address, WIZ_TOKEN.address).call()


def removeLiquidity(w3, account, router_proxy):
    pair_address = get_pair_address(w3, router_proxy)
    liquidity_token = Erc20Token(
        ticker="UNI-V2",
        wei_ticker="UNI-V2 WEI",
        addresses={NETWORK.name: pair_address},
        network_name=NETWORK.name
    )
    amount = get_token_balance(w3, account, liquidity_token)

    approve(w3, account, router_proxy.address, amount.as_wei, liquidity_token)

    min_eth = 1
    min_tokens = 1
    deadline = generateDeadline(w3)
    transaction_params = {
        "from": account.address,
        "gas_price": w3.eth.generateGasPrice(),
        "gas": GAS_LIMIT,
    }

    tx_hash = send_raw_transaction(
        w3,
        account,
        router_proxy.functions.removeLiquidityETH,
        WIZ_TOKEN.address,
        amount.as_wei,
        min_tokens,
        min_eth,
        account.address,
        deadline,
        **transaction_params,
    )
    wait_for_transaction(w3, tx_hash)


@pytest.fixture
def infura():
    assert INFURA_PROJECT_ID
    return Infura.make(NETWORK, INFURA_PROJECT_ID)


@pytest.fixture
def provide_liquidity(infura, create_account, uniswap):
    account = create_account()
    w3 = make_web3_provider(infura.url, account)

    fund_account(account, w3)
    tx_hash = mint_tokens(w3, account, WIZ_TOKEN)
    wait_for_transaction(w3, tx_hash)

    current_rate = uniswap.get_current_rate(TokenAmount(1000, WIZ_TOKEN))

    router_proxy = w3.eth.contract(
        abi=uniswap_contracts.UNISWAP_ROUTER02_ABI,
        address=Uniswap.ROUTER02_ADDRESS,
    )
    addLiquidity(w3, account, router_proxy, current_rate)
    yield
    removeLiquidity(w3, account, router_proxy)
    empty_account(w3, account)


@pytest.fixture
def funded_account(test_account, uniswap):
    fund_account(test_account, uniswap.w3)
    yield test_account
    empty_account(uniswap.w3, test_account)


@pytest.fixture
def uniswap(test_account, infura):
    w3 = make_web3_provider(infura.url, test_account)
    return Uniswap(w3)


def test_buy_tokens(funded_account, provide_liquidity, uniswap):
    w3 = uniswap.w3
    wiz_balance_before = get_token_balance(w3, funded_account, WIZ_TOKEN)
    buy_amount = TokenAmount(1, WIZ_TOKEN)
    tx_hash = uniswap.buy_tokens(funded_account, buy_amount)
    wait_for_transaction(w3, tx_hash)
    wiz_balance_after = get_token_balance(w3, funded_account, WIZ_TOKEN)
    assert wiz_balance_after == wiz_balance_before + buy_amount


def test_cannot_buy_zero_tokens(funded_account, provide_liquidity, uniswap):
    with pytest.raises(ExchangeError):
        uniswap.buy_tokens(funded_account, TokenAmount(0, WIZ_TOKEN))


def test_cannot_buy_without_eth(test_account, provide_liquidity, uniswap):
    with pytest.raises(ValueError):
        uniswap.buy_tokens(test_account, TokenAmount(1, WIZ_TOKEN))
