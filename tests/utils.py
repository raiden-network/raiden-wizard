from math import ceil

FAUCET_ACCOUNT = "0x3918d37E2f28F5B22f9f650556AD9D4590960018"


def empty_accounts(w3, accounts):
    gas = 21000

    for account in accounts:
        balance = w3.eth.getBalance(account.address)
        nonce = w3.eth.getTransactionCount(account.address, "pending")
        gas_price = w3.eth.generateGasPrice()
        value = balance - ceil(gas * gas_price)
        if value <= 0:
            continue

        # Making sure that our faucet does not deplete so fast
        signed = w3.eth.account.signTransaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gasPrice": gas_price,
                "gas": gas,
                "to": FAUCET_ACCOUNT,
                "value": value,
            },
            account.private_key,
        )
        w3.eth.sendRawTransaction(signed.rawTransaction)
