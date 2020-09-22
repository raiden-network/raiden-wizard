import sys
import time
from pathlib import Path

import psutil
import pytest
import requests
from eth_utils import to_bytes
from tests.fixtures import create_account, test_password
from tests.integration import kyber_snapshot_addresses

from raiden_installer.account import Account
from raiden_installer.ethereum_rpc import make_web3_provider
from raiden_installer.kyber.web3.constants import NETWORK_ADDRESS_MODULES_BY_CHAIN_ID
from raiden_installer.network import NETWORK_CLASSES, Network
from raiden_installer.token_exchange import ExchangeError, Kyber
from raiden_installer.tokens import Erc20Token, TokenAmount
from raiden_installer.transactions import get_token_balance
from raiden_installer.utils import wait_for_transaction

FAKE_BLOCKCHAIN_PATH = Path("tests", "fake_blockchain")
PORT = "8546"
CHAIN_ID = 1337
# Args as specified by the Kyber snapshot documentation
GANACHE_COMMAND = [
    "node",
    "node_modules/ganache-cli/cli.js",
    "--db",
    "node_modules/kyber-network-workshop/db",
    "--accounts",
    "10",
    "--defaultBalanceEther",
    "1000",
    "--mnemonic",
    "gesture rather obey video awake genuine patient base soon parrot upset lounge",
    "--networkId",
    "5777",
    "--port",
    PORT
]

# Prefilled account from Kyber Ganache snapshot
WALLET_PRIVATE_KEY = 0x979d8b20000da5832fc99c547393fdfa5eef980c77bfb1decb17c59738d99471

KNC_TOKEN = Erc20Token(
    ticker="KNC",
    wei_ticker="KEI",
    addresses={"ganache": kyber_snapshot_addresses.TokenAddress.KNC.value},
    network_name="ganache"
)


def take_snapshot():
    body = dict(jsonrpc="2.0", method="evm_snapshot", params=[], id=1)
    response = requests.post(f"http://localhost:{PORT}", json=body)
    return response.json()["result"]


def revert_to_snapshot(snapshot_id):
    body = dict(jsonrpc="2.0", method="evm_revert", params=[snapshot_id], id=1)
    requests.post(f"http://localhost:{PORT}", json=body)


@pytest.fixture
def test_account(monkeypatch, create_account):
    monkeypatch.setattr(Account, "generate_private_key", lambda: to_bytes(WALLET_PRIVATE_KEY))
    return create_account()


@pytest.fixture
def patch_kyber_support(monkeypatch):
    monkeypatch.setitem(NETWORK_ADDRESS_MODULES_BY_CHAIN_ID, CHAIN_ID, kyber_snapshot_addresses)


@pytest.fixture
def patch_network(monkeypatch):
    class Ganache(Network):
        pass

    monkeypatch.setitem(NETWORK_CLASSES, "ganache", Ganache)
    monkeypatch.setitem(Network.CHAIN_ID_MAPPING, "ganache", CHAIN_ID)


@pytest.fixture(scope="module")
def kyber_chain():
    proc = psutil.Popen(
        GANACHE_COMMAND,
        cwd=str(FAKE_BLOCKCHAIN_PATH)
    )
    time.sleep(2)
    yield
    proc.terminate()
    proc.wait()


@pytest.fixture
def kyber(test_account: Account, kyber_chain, patch_network):
    snapshot_id = take_snapshot()
    w3 = make_web3_provider(f"http://localhost:{PORT}", test_account)
    yield Kyber(w3)
    revert_to_snapshot(snapshot_id)


def test_buy_tokens(test_account, patch_kyber_support, kyber):
    knc_balance_before = get_token_balance(kyber.w3, test_account, KNC_TOKEN)
    buy_amount = TokenAmount(10, KNC_TOKEN)
    tx_hash = kyber.buy_tokens(test_account, buy_amount)
    kyber.w3.eth.waitForTransactionReceipt(tx_hash)
    knc_balance_after = get_token_balance(kyber.w3, test_account, KNC_TOKEN)
    assert knc_balance_after == knc_balance_before + buy_amount


def test_cannot_buy_on_unsupported_network(test_account, kyber):
    with pytest.raises(ExchangeError):
        kyber.buy_tokens(test_account, TokenAmount(10, KNC_TOKEN))


def test_cannot_buy_zero_tokens(test_account, patch_kyber_support, kyber):
    with pytest.raises(ExchangeError):
        kyber.buy_tokens(test_account, TokenAmount(0, KNC_TOKEN))


def test_cannot_buy_without_eth(test_account, patch_kyber_support, kyber):
    tx = {
        "to": "0x0000000000000000000000000000000000000000",
        "from": test_account.address,
        "value": test_account.get_ethereum_balance(kyber.w3).as_wei,
        "gasPrice": 0,
    }
    tx_hash = kyber.w3.eth.sendTransaction(tx)
    kyber.w3.eth.waitForTransactionReceipt(tx_hash)

    with pytest.raises(ValueError):
        kyber.buy_tokens(test_account, TokenAmount(10, KNC_TOKEN))


def test_cannot_buy_without_enough_liquidity(test_account, patch_kyber_support, kyber):
    with pytest.raises(ExchangeError):
        kyber.buy_tokens(test_account, TokenAmount(10000000, KNC_TOKEN))
