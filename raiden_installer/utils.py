import requests

from raiden_installer import log
from raiden_contracts.contract_manager import get_contracts_deployment_info

from raiden_installer.tokens import EthereumAmount, Wei


def get_contract_address(chain_id, contract_name):
    try:
        network_contracts = get_contracts_deployment_info(chain_id)
        assert network_contracts
        return network_contracts["contracts"][contract_name]["address"]
    except (TypeError, AssertionError) as exc:
        log.warn(str(exc))
        return "0x0"


def estimate_gas(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": int(w3.net.version),
        "nonce": w3.eth.getTransactionCount(account.address),
    }
    transaction_params.update(**kw)
    result = contract_function(*args)
    transaction = result.buildTransaction(transaction_params)
    return w3.eth.estimateGas(transaction)


def send_raw_transaction(w3, account, contract_function, *args, **kw):
    transaction_params = {
        "chainId": int(w3.net.version),
        "nonce": w3.eth.getTransactionCount(account.address),
        "gasPrice": kw.pop("gas_price", w3.eth.gasPrice),
        "gas": kw.pop("gas", None),
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

    return w3.eth.waitForTransactionReceipt(tx_hash)


def check_eth_node_responsivity(url):
    try:
        body = dict(jsonrpc="2.0", method="web3_clientVersion", params=[], id=1)
        response = requests.post(url, json=body)
        if(response.status_code == 401):
            raise ValueError(
                "Unauthorized to make requests to ethereum node."
                "Maybe the Infura project ID is wrong?"
            )
    except requests.RequestException as e:
        raise ValueError(str(e) or "Unspecified Request Exception")
