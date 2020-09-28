import math
import os
import time

import requests
from eth_typing import Address
from eth_utils import to_canonical_address, to_checksum_address
from web3 import Web3
from web3.exceptions import TransactionNotFound

from raiden_contracts.contract_manager import get_contracts_deployment_info
from raiden_installer import log
from raiden_installer.constants import REQUIRED_BLOCK_CONFIRMATIONS, WEB3_TIMEOUT
from raiden_installer.tokens import EthereumAmount, Wei


class TransactionTimeoutError(Exception):
    pass


def recover_ld_library_env_path():  # pragma: no cover
    """This works around an issue that `webbrowser.open` fails inside a
    PyInstaller binary.
    See: https://github.com/pyinstaller/pyinstaller/issues/3668
    """
    lp_key = "LD_LIBRARY_PATH"
    lp_orig = os.environ.get(lp_key + "_ORIG")
    if lp_orig is not None:
        os.environ[lp_key] = lp_orig
    else:
        lp = os.environ.get(lp_key)
        if lp is not None:
            os.environ.pop(lp_key)


def get_contract_address(chain_id, contract_name) -> Address:
    try:
        network_contracts = get_contracts_deployment_info(chain_id)
        assert network_contracts
        return to_canonical_address(network_contracts["contracts"][contract_name]["address"])
    except (TypeError, AssertionError, KeyError) as exc:
        log.warn(str(exc))
        raise ValueError(f"{contract_name} does not exist on chain id {chain_id}") from exc


def estimate_gas(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": w3.eth.chainId,
        "nonce": w3.eth.getTransactionCount(account.address, "pending"),
    }
    transaction_params.update(**kw)
    result = contract_function(*args)
    transaction = result.buildTransaction(transaction_params)
    return w3.eth.estimateGas(transaction)


def send_raw_transaction(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": w3.eth.chainId,
        "nonce": w3.eth.getTransactionCount(account.address, "pending"),
        "gasPrice": kw.pop("gas_price", (w3.eth.generateGasPrice())),
        "gas": kw.pop("gas", None),
        "from": to_checksum_address(kw.pop("from", account.address))
    }

    transaction_params.update(**kw)
    if not transaction_params.get("gas"):
        transaction_params["gas"] = estimate_gas(w3, account, contract_function, *args, **kw)

    gas_price = transaction_params["gasPrice"]
    gas = transaction_params["gas"]
    value = transaction_params.get("value", 0)

    estimated_cost = EthereumAmount(Wei((gas * gas_price) + value))

    log.debug(f"Estimated cost: {estimated_cost.formatted}")

    result = contract_function(*args)
    transaction_data = result.buildTransaction(transaction_params)
    signed = w3.eth.account.signTransaction(transaction_data, account.private_key)
    tx_hash = w3.eth.sendRawTransaction(signed.rawTransaction)
    log.debug(f"transaction hash: {tx_hash.hex()}")
    return tx_hash


def wait_for_transaction(w3: Web3, transaction_hash) -> None:
    log.debug("wait for block with transaction to be fetched")
    time_start = time.time()
    block_with_transaction = math.inf
    current_block = w3.eth.blockNumber

    while current_block < block_with_transaction + REQUIRED_BLOCK_CONFIRMATIONS:
        if time.time() - time_start >= WEB3_TIMEOUT:
            raise TransactionTimeoutError(
                f"Tx with hash {transaction_hash} was not found after {WEB3_TIMEOUT} seconds"
            )
        try:
            tx_receipt = w3.eth.getTransactionReceipt(transaction_hash)
            block_with_transaction = tx_receipt["blockNumber"]
        except TransactionNotFound:
            pass

        current_block = w3.eth.blockNumber
        time.sleep(1)


def check_eth_node_responsivity(url):
    try:
        body = dict(jsonrpc="2.0", method="web3_clientVersion", params=[], id=1)
        response = requests.post(url, json=body)
        if response.status_code == 401:
            raise ValueError(
                "Unauthorized to make requests to ethereum node."
                "Maybe the Infura project ID is wrong?"
            )
    except requests.RequestException as exc:
        raise ValueError(str(exc) or "Unspecified Request Exception") from exc
