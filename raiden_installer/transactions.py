from eth_utils import to_checksum_address
from ethtoken.abi import EIP20_ABI
from web3 import Web3

from raiden_contracts.constants import CONTRACT_USER_DEPOSIT, CONTRACT_CUSTOM_TOKEN
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path

from raiden_installer.account import Account
from raiden_installer.tokens import TokenAmount, Wei, Erc20Token
from raiden_installer.utils import get_contract_address, send_raw_transaction


GAS_REQUIRED_FOR_DEPOSIT: int = 200_000
GAS_REQUIRED_FOR_APPROVE: int = 70_000
GAS_REQUIRED_FOR_MINT: int = 100_000


def _make_deposit_proxy(w3: Web3, token: Erc20Token):
    contract_manager = ContractManager(contracts_precompiled_path())
    contract_address = get_contract_address(int(w3.net.version), CONTRACT_USER_DEPOSIT)
    proxy = w3.eth.contract(
        address=contract_address, abi=contract_manager.get_contract_abi(CONTRACT_USER_DEPOSIT)
    )

    service_token_address = to_checksum_address(proxy.functions.token().call())

    if service_token_address != to_checksum_address(token.address):
        raise ValueError(f"{token.ticker} is at {token.address}, expected {service_token_address}")
    return proxy


def _make_token_proxy(w3: Web3, token: Erc20Token):
    return w3.eth.contract(address=to_checksum_address(token.address), abi=EIP20_ABI)


def mint_tokens(w3: Web3, account: Account, token: Erc20Token):
    contract_manager = ContractManager(contracts_precompiled_path())
    token_proxy = w3.eth.contract(
        address=to_checksum_address(token.address),
        abi=contract_manager.get_contract_abi(CONTRACT_CUSTOM_TOKEN),
    )

    return send_raw_transaction(
        w3, account, token_proxy.functions.mint, token.supply, gas=GAS_REQUIRED_FOR_MINT
    )


def deposit_service_tokens(w3: Web3, account: Account, token: Erc20Token, amount: Wei):
    token_proxy = _make_token_proxy(w3=w3, token=token)
    deposit_proxy = _make_deposit_proxy(w3=w3, token=token)

    current_deposit_amount = TokenAmount(
        Wei(deposit_proxy.functions.total_deposit(account.address).call()), token
    )

    new_deposit_amount = TokenAmount(amount, token)

    total_deposit = current_deposit_amount + new_deposit_amount

    send_raw_transaction(
        w3,
        account,
        token_proxy.functions.approve,
        deposit_proxy.address,
        total_deposit.as_wei,
        gas=GAS_REQUIRED_FOR_APPROVE,
    )

    return send_raw_transaction(
        w3,
        account,
        deposit_proxy.functions.deposit,
        account.address,
        total_deposit.as_wei,
        gas=GAS_REQUIRED_FOR_DEPOSIT,
    )


def get_token_balance(w3: Web3, account: Account, token: Erc20Token) -> TokenAmount:
    token_proxy = _make_token_proxy(w3=w3, token=token)
    amount = Wei(token_proxy.functions.balanceOf(account.address).call())

    return TokenAmount(amount, token)


def get_token_deposit(w3: Web3, account: Account, token: Erc20Token) -> TokenAmount:
    deposit_proxy = _make_deposit_proxy(w3=w3, token=token)
    amount = Wei(deposit_proxy.functions.effectiveBalance(account.address).call())

    return TokenAmount(amount, token)


def get_total_token_owned(w3: Web3, account: Account, token: Erc20Token) -> TokenAmount:
    return get_token_balance(w3, account, token) + get_token_deposit(w3, account, token)
