#!/usr/bin/env python
import glob
import os
import webbrowser
from getpass import getpass
from math import ceil
from time import sleep

from abi import ERC20_ABI, UDC_ABI
from eth_keyfile import load_keyfile
from eth_utils import to_checksum_address, to_hex
from web3 import HTTPProvider, Web3
from web3.exceptions import TransactionNotFound
from web3.gas_strategies.time_based import fast_gas_price_strategy

w3 = Web3(
    HTTPProvider(os.environ.get("ETH_RPC", "http://9.geth.mainnet.ethnodes.brainbot.com:8545"))
)

KEYSTORE_PATH = os.path.expanduser("~/.ethereum/keystore/*")

DAI = w3.eth.contract("0x6B175474E89094C44Da98b954EedeAC495271d0F", abi=ERC20_ABI,)
RDN = w3.eth.contract("0x255Aa6DF07540Cb5d3d297f0D0D4D84cb52bc8e6", abi=ERC20_ABI,)
UDC = w3.eth.contract("0x15ac371adE21c4F31Da36A4Cf9A0ef35aFdE7a9F", abi=UDC_ABI)

# additional margin of gas estimation for contract calls
OVERSHOOT = 1.05


def overshooting_fast_gasprice(*args, **kwargs):
    return ceil(fast_gas_price_strategy(*args, **kwargs) * OVERSHOOT)


def unlock(encrypted_key, known_passwords):
    account_address = encrypted_key["address"]
    for known in known_passwords:
        try:
            private_key = w3.eth.account.decrypt(encrypted_key, known)
            if private_key is not None:
                return private_key
        except ValueError:
            pass

    attempts = 5
    try:
        while attempts > 0:
            password = getpass(f"Please give your password for {account_address}: ")
            known_passwords.add(password)
            try:
                private_key = w3.eth.account.decrypt(encrypted_key, password)
                if private_key is not None:
                    return private_key
            except ValueError:
                attempts -= 1
    except KeyboardInterrupt:
        pass
    print(f"Unlocking {account_address} failed.")


def get_receiving_address():
    address = None
    while address is None:
        address = input("Please type the receiver address: ")
        if address == to_checksum_address(address):
            return to_checksum_address(address)
        address = None


def sign_and_poll(tx, private_key):
    signed = w3.eth.account.signTransaction(tx, private_key=private_key)
    txhash = w3.eth.sendRawTransaction(signed.rawTransaction)
    return poll(txhash)


def poll(txhash):
    webbrowser.open_new_tab(f"https://etherscan.io/tx/{to_hex(txhash)}")
    mined = None
    while mined is None:
        try:
            mined = w3.eth.getTransaction(txhash)
            if mined["blockNumber"] is not None:
                return
            else:
                mined = None
        except TransactionNotFound:
            pass
        finally:
            sleep(0.5)


class AccountDrainer:
    def __init__(self):
        w3.eth.setGasPriceStrategy(fast_gas_price_strategy)
        self.gasprice = w3.eth.generateGasPrice()
        self.receiver = None
        self.accounts_with_balance = []

        self.collect_keystore_files()
        for address in self.accounts_dict.keys():
            self.collect_balances(address)
        self.unlock_accounts_with_balance()

    def collect_keystore_files(self):
        self.accounts_dict = dict()
        keystore_files = glob.glob(KEYSTORE_PATH)
        for keystore_file in keystore_files:
            keyfile = load_keyfile(keystore_file)
            self.accounts_dict[to_checksum_address("0x" + keyfile["address"])] = {
                "keyfile_json": keyfile,
                "keystore_file": keystore_file,
            }

    def collect_balances(self, address):
        eth_balance = w3.eth.getBalance(to_checksum_address(address))
        dai_balance = DAI.functions.balanceOf(address).call()
        rdn_balance = RDN.functions.balanceOf(address).call()
        udc_balance = UDC.functions.balances(address).call()

        balances = dict(ETH=eth_balance, DAI=dai_balance, RDN=rdn_balance, UDC=udc_balance,)
        self.accounts_dict[address]["Balances"] = balances
        self.accounts_dict[address]["Ignore"] = not any(
            (eth_balance, dai_balance, rdn_balance, udc_balance)
        )
        if not self.accounts_dict[address]["Ignore"]:
            print(
                f"{address}:\n"
                f"\tETH: {eth_balance}\n"
                f"\tDAI: {dai_balance}\n"
                f"\tRDN: {rdn_balance}\n"
                f"\tUDC: {udc_balance}\n"
            )
            self.accounts_with_balance.append(address)
            self.accounts_with_balance = list(set(self.accounts_with_balance))

    def unlock_accounts_with_balance(self):
        known_passwords = set()
        accounts_with_balance_and_pk = []
        for address in self.accounts_with_balance:
            keyfile = self.accounts_dict[address]["keyfile_json"]
            private_key = unlock(keyfile, known_passwords)
            if private_key is not None:
                self.accounts_dict[address]["private_key"] = private_key
                accounts_with_balance_and_pk.append(address)
        self.accounts_with_balance = accounts_with_balance_and_pk

        for address in self.accounts_with_balance:
            if "private_key" in self.accounts_dict[address]:
                print(f"{address} unlocked")
            else:
                print(f"Ignoring {address}.")

    def sweep(self):
        if self.receiver is None:
            self.receiver = get_receiving_address()
        while self.work_left():
            try:
                for address in self.accounts_with_balance:
                    if self.udc_empty(address):
                        self.forward_rdn(address)
                        self.forward_dai(address)
                        self.forward_eth(address)
                    else:
                        self.empty_udc(address)
                    self.collect_balances(address)
            except KeyboardInterrupt:
                print("Interrupted.")
                breakpoint()
                return
            except Exception:
                import pdb

                pdb.post_mortem()
            finally:
                sleep(0.5)

    def work_left(self):
        if any(not self.udc_empty(address) for address in self.accounts_with_balance):
            print(f"Draining UDC")
            return True
        for address in self.accounts_with_balance:
            if address.lower() == self.receiver.lower():
                continue
            if self.has_any_balance_left(address):
                print(f"continuing to drain {address}:")
                return True
        return False

    def _has(self, currency, address):
        return self.accounts_dict[address]["Balances"][currency] > 0

    def has_rdn(self, address):
        return self._has("RDN", address)

    def has_dai(self, address):
        return self._has("DAI", address)

    def has_eth(self, address):
        return self._has("ETH", address)

    def has_any_balance_left(self, address):
        return any((self.has_rdn(address), self.has_dai(address), self.has_eth(address)))

    def udc_empty(self, address):
        return self.accounts_dict[address]["Balances"]["UDC"] == 0

    def empty_udc(self, address):
        amount = self.accounts_dict[address]["Balances"]["UDC"]
        if amount > 0:
            withdraw_planned = UDC.functions.withdraw_plans(address).call()
            private_key = self.accounts_dict[address]["private_key"]
            nonce = w3.eth.getTransactionCount(address, "pending")
            if withdraw_planned != [0, 0]:
                planned_amount, release_block = withdraw_planned
                current_block = w3.eth.blockNumber
                print(
                    f"Withdraw {planned_amount} @ {release_block} / {current_block} "
                    f"planned for {address}"
                )
                if current_block > release_block:
                    print("Withdrawing")
                    withdraw_call = UDC.functions.withdraw(planned_amount)
                    withdraw_gas = withdraw_call.estimateGas({"from": address})
                    withdraw_tx = withdraw_call.buildTransaction(
                        {
                            "from": address,
                            "gas": withdraw_gas,
                            "gasPrice": self.gasprice,
                            "nonce": nonce,
                        }
                    )
                    sign_and_poll(withdraw_tx, private_key)
                else:
                    print(
                        f"For {address} we have to wait "
                        f"{release_block - current_block} blocks to withdraw"
                    )
                    return
            else:
                print(f"Planning withdraw for {address} and {amount}")
                plan_withdraw_call = UDC.functions.planWithdraw(amount)
                plan_withdraw_gas = plan_withdraw_call.estimateGas({"from": address})
                plan_withdraw_tx = plan_withdraw_call.buildTransaction(
                    {
                        "from": address,
                        "gas": plan_withdraw_gas,
                        "gasPrice": self.gasprice,
                        "nonce": nonce,
                    }
                )
                sign_and_poll(plan_withdraw_tx, private_key)

    def forward_eth(self, address):
        if address.lower() == self.receiver.lower():
            return
        amount = w3.eth.getBalance(address)
        if amount > 0:
            print(f"Moving {amount} ETH from {address} to {self.receiver}.")
            gas_eth = 21000
            nonce = w3.eth.getTransactionCount(address, "pending")
            private_key = self.accounts_dict[address]["private_key"]
            value = amount - ceil(gas_eth * self.gasprice)
            if value <= 0:
                print(f"Not worth it, value after gas is {value} for {address}.")
                return
            signed = w3.eth.account.signTransaction(
                {
                    "from": address,
                    "nonce": nonce,
                    "gasPrice": self.gasprice,
                    "gas": gas_eth,
                    "to": self.receiver,
                    "value": value,
                },
                private_key,
            )
            txhash = w3.eth.sendRawTransaction(signed.rawTransaction)
            poll(txhash)

    def forward_dai(self, address):
        if address.lower() == self.receiver.lower():
            return
        amount = self.accounts_dict[address]["Balances"]["DAI"]
        if amount > 0:
            nonce = w3.eth.getTransactionCount(address, "pending")
            private_key = self.accounts_dict[address]["private_key"]

            dai_transfer_call = DAI.functions.transfer(self.receiver, amount)
            dai_transfer_gas = dai_transfer_call.estimateGas({"from": address})
            dai_transfer_tx = dai_transfer_call.buildTransaction(
                {
                    "from": address,
                    "gas": dai_transfer_gas,
                    "gasPrice": self.gasprice,
                    "nonce": nonce,
                }
            )
            sign_and_poll(dai_transfer_tx, private_key)

    def forward_rdn(self, address):
        if address.lower() == self.receiver.lower():
            return
        amount = self.accounts_dict[address]["Balances"]["RDN"]
        if amount > 0:
            nonce = w3.eth.getTransactionCount(w3.toChecksumAddress(address), "pending")
            private_key = self.accounts_dict[address]["private_key"]

            rdn_transfer_call = RDN.functions.transfer(self.receiver, amount)
            rdn_transfer_gas = rdn_transfer_call.estimateGas({"from": address})
            rdn_transfer_tx = rdn_transfer_call.buildTransaction(
                {
                    "from": address,
                    "gas": rdn_transfer_gas,
                    "gasPrice": self.gasprice,
                    "nonce": nonce,
                }
            )
            sign_and_poll(rdn_transfer_tx, private_key)


if __name__ == "__main__":
    drainer = AccountDrainer()
    drainer.sweep()
