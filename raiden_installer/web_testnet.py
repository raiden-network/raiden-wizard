import json
import sys

from tornado.web import url

from raiden_installer import log
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.ethereum_rpc import make_web3_provider
from raiden_installer.shared_handlers import AsyncTaskHandler, main, try_unlock
from raiden_installer.tokens import Erc20Token, EthereumAmount
from raiden_installer.transactions import get_token_balance, mint_tokens
from raiden_installer.utils import wait_for_transaction

SETTINGS = "demo_env"


class TestnetAsyncTaskHandler(AsyncTaskHandler):
    def initialize(self):
        super().initialize()
        self.actions.update({
            "fund": self._run_funding
        })

    def _send_next_step(self, message_text, title, step):
        if not isinstance(message_text, list):
            message_text = [message_text]
        body = {"type": "next-step", "text": message_text, "title": title, "step": step}
        self.write_message(json.dumps(body))
        log.info(" ".join(message_text))
        log.info(f"Update progress to step {step}: {title}")

    def _run_funding(self, **kw):
        try:
            configuration_file_name = kw.get("configuration_file_name")
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        except Exception as exc:
            self._send_error_message(str(exc))
            return

        network = configuration_file.network

        if not network.FAUCET_AVAILABLE:
            self._send_error_message(
                f"Can not run automatic funding for {network.capitalized_name}"
            )
            return

        account = configuration_file.account
        try_unlock(account)
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        self._send_status_update(f"Obtaining {network.capitalized_name} ETH through faucet")
        network.fund(account)
        balance = account.wait_for_ethereum_funds(w3=w3, expected_amount=EthereumAmount(0.01))
        self._send_status_update(f"Account funded with {balance.formatted}")

        service_token = Erc20Token.find_by_ticker(
            self.installer_settings.service_token.ticker, self.installer_settings.network
        )

        if self.installer_settings.service_token.mintable:
            self._send_next_step(
                f"Minting {service_token.ticker}",
                f"Fund Account with {service_token.ticker}",
                3,
            )
            transaction_receipt = mint_tokens(w3, account, service_token)
            wait_for_transaction(w3, transaction_receipt)

        service_token_balance = get_token_balance(w3, account, service_token)

        if service_token_balance.as_wei > 0:
            self._deposit_to_udc(w3, account, service_token, service_token_balance)

        if self.installer_settings.transfer_token.mintable:
            transfer_token = Erc20Token.find_by_ticker(
                self.installer_settings.transfer_token.ticker, self.installer_settings.network
            )
            self._send_next_step(
                f"Minting {transfer_token.ticker}",
                f"Fund Account with {transfer_token.ticker}",
                4,
            )
            transaction_receipt = mint_tokens(w3, account, transfer_token)
            wait_for_transaction(w3, transaction_receipt)

        self._send_redirect(self.reverse_url("launch", configuration_file_name))


if __name__ == "__main__":
    additional_handlers = [
        url(r"/ws", TestnetAsyncTaskHandler, name="websocket"),
    ]

    # port = (sum(ord(c) for c in "RAIDEN_WIZARD_TESTNET") + 1000) % 2 ** 16 - 1 = 2640
    main(2640, SETTINGS, additional_handlers)
