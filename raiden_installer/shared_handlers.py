import json
import os
import sys
import time
from glob import glob
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import wtforms
from eth_utils import to_checksum_address
from tornado.web import Application, HTTPError, RequestHandler
from tornado.websocket import WebSocketHandler
from wtforms.validators import EqualTo
from wtforms_tornado import Form

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_installer import available_settings, default_settings, log
from raiden_installer.base import Account, RaidenConfigurationFile
from raiden_installer.ethereum_rpc import EthereumRPCProvider, Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.raiden import RaidenClient, RaidenClientError, temporary_passphrase_file
from raiden_installer.tokens import Erc20Token, RequiredAmounts
from raiden_installer.transactions import (
    deposit_service_tokens,
    get_token_balance,
    get_token_deposit,
    get_total_token_owned,
)
from raiden_installer.utils import check_eth_node_responsivity, wait_for_transaction

EIP20_ABI = ContractManager(contracts_precompiled_path()).get_contract_abi("StandardToken")
PASSPHRASE: Optional[str] = None

AVAILABLE_NETWORKS = [Network.get_by_name(n) for n in ["mainnet", "ropsten", "goerli"]]
DEFAULT_NETWORK = Network.get_default()


def try_unlock(account):
    if account.check_passphrase(PASSPHRASE):
        account.passphrase = PASSPHRASE


class QuickSetupForm(Form):
    network = wtforms.HiddenField("Network", default=DEFAULT_NETWORK.name)
    use_rsb = wtforms.HiddenField(
        "Use Raiden Service Bundle", default=default_settings.monitoring_enabled
    )
    endpoint = wtforms.StringField("Infura Project ID/RPC Endpoint")

    def validate_network(self, field):
        network_name = field.data
        if network_name not in [n.name for n in AVAILABLE_NETWORKS]:
            raise wtforms.ValidationError(f"Can not run quick setup raiden with {network_name}")

    def validate_endpoint(self, field):
        data = field.data.strip()
        parsed_url = urlparse(data)
        is_valid_url = bool(parsed_url.scheme) and bool(parsed_url.netloc)

        if not (Infura.is_valid_project_id_or_endpoint(data) or is_valid_url):
            raise wtforms.ValidationError("Not a valid URL nor Infura Project ID")


class PasswordForm(Form):
    passphrase1 = wtforms.PasswordField(validators=[EqualTo("passphrase2")])
    passphrase2 = wtforms.PasswordField(validators=[EqualTo("passphrase1")])


class AsyncTaskHandler(WebSocketHandler):
    def initialize(self):
        self.installer_settings_name = self.settings.get("installer_settings_name")
        self.installer_settings = available_settings[self.installer_settings_name]
        self.actions = {
            "close": self._run_close,
            "launch": self._run_launch,
            "setup": self._run_setup,
            "unlock": self._run_unlock,
            "create_wallet": self._run_create_wallet,
        }

    def on_message(self, message):
        data = json.loads(message)
        method = data.pop("method", None)
        action = method and self.actions.get(method)
        return action and action(**data)

    def _send_status_update(self, message_text, icon=None):
        if not isinstance(message_text, list):
            message_text = [message_text]
        body = {"type": "status-update", "text": message_text}
        if icon:
            body["icon"] = icon
        self.write_message(json.dumps(body))
        log.info(" ".join(message_text))

    def _send_error_message(self, error_message):
        self.write_message(json.dumps({"type": "error-message", "text": [error_message]}))
        log.error(error_message)

    def _send_task_complete(self, message_text):
        self.write_message(json.dumps({"type": "task-complete", "text": [message_text]}))
        log.info(message_text)

    def _send_redirect(self, redirect_url):
        self.write_message(json.dumps({"type": "redirect", "redirect_url": redirect_url}))
        log.info(f"Redirecting to {redirect_url}")

    def _send_summary(self, text, **kw):
        if not isinstance(text, list):
            text = [text]
        message = {"type": "summary", "text": text}
        icon = kw.get("icon")
        if icon:
            message["icon"] = icon
        self.write_message(message)

    def _send_txhash_message(self, text, tx_hash):
        if not isinstance(text, list):
            text = [text]
        message = {"type": "hash", "text": text, "tx_hash": tx_hash}
        self.write_message(message)
        log.info(f"Waiting for confirmation of txhash {tx_hash}")

    def _run_close(self, **kw):
        sys.exit()

    def _run_udc_deposit(self, w3, account, service_token, service_token_balance):
        self._send_status_update(
            f"Making deposit of {service_token_balance.formatted} to the "
            "User Deposit Contract"
        )
        self._send_status_update(f"This might take a few minutes")
        transaction_receipt = deposit_service_tokens(
            w3=w3,
            account=account,
            token=service_token,
            amount=service_token_balance.as_wei,
        )
        wait_for_transaction(w3, transaction_receipt)
        service_token_deposited = get_token_deposit(
            w3=w3, account=account, token=service_token
        )
        self._send_status_update(
            f"Total amount deposited at UDC: {service_token_deposited.formatted}"
        )

    def _run_unlock(self, **kw):
        passphrase = kw.get("passphrase")
        keystore_file_path = kw.get("keystore_file_path")
        account = Account(keystore_file_path)
        if account.check_passphrase(passphrase):
            global PASSPHRASE
            PASSPHRASE = kw.get("passphrase")
            self._send_redirect(kw.get("return_to"))
        else:
            self._send_error_message("Incorrect passphrase, try again.")

    def _run_create_wallet(self, **kw):
        form = PasswordForm(passphrase1=kw.get("passphrase1"), passphrase2=kw.get("passphrase2"))
        network_name = kw.get("network_name")
        if form.validate():
            self._send_status_update("Generating new wallet file for Raiden")
            global PASSPHRASE
            PASSPHRASE = form.data["passphrase1"].strip()
            account = Account.create(passphrase=PASSPHRASE)

            self._send_redirect(
                self.reverse_url("setup", account.keystore_file_path)
            )

    def _run_setup(self, **kw):
        account_file = kw.get("account_file")
        account = Account(account_file, passphrase=PASSPHRASE)
        form = QuickSetupForm(endpoint=kw.get("endpoint"), network=kw.get("network"))
        if form.validate():
            self._send_status_update("Generating new wallet and configuration file for raiden")

            network = Network.get_by_name(form.data["network"])
            url_or_infura_id = form.data["endpoint"].strip()

            if Infura.is_valid_project_id_or_endpoint(url_or_infura_id):
                ethereum_rpc_provider = Infura.make(network, url_or_infura_id)
            else:
                ethereum_rpc_provider = EthereumRPCProvider(url_or_infura_id)

            try:
                check_eth_node_responsivity(ethereum_rpc_provider.url)
            except ValueError as e:
                self._send_error_message(f"Ethereum node unavailable: {e}.")
                return

            conf_file = RaidenConfigurationFile(
                account.keystore_file_path,
                self.installer_settings_name,
                ethereum_rpc_provider.url,
                routing_mode="pfs" if form.data["use_rsb"] else "local",
                enable_monitoring=form.data["use_rsb"],
            )
            conf_file.save()

            self._send_redirect(self.reverse_url("account", conf_file.file_name))
        else:
            self._send_error_message(f"Failed to create account. Error: {form.errors}")

    def _run_launch(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        raiden_client = RaidenClient.get_client(self.installer_settings)

        if not raiden_client.is_installed:
            self._send_status_update(f"Downloading and installing raiden {raiden_client.release}")
            raiden_client.install()
            self._send_status_update("Installation complete")

        account = configuration_file.account
        try_unlock(account)
        if account.passphrase is None:
            return self.render(
                "account_unlock.html",
                keystore_file_path=account.keystore_file_path,
                return_to=f"/launch/{configuration_file_name}",
            )

        self._send_status_update(
            "Launching Raiden, this might take a couple of minutes, do not close the browser"
        )

        with temporary_passphrase_file(PASSPHRASE) as passphrase_file:
            if not raiden_client.is_running:
                raiden_client.launch(configuration_file, passphrase_file)

            try:
                raiden_client.wait_for_web_ui_ready(
                    status_callback=lambda stat: log.info(str(stat))
                )
                self._send_task_complete("Raiden is ready!")
                self._send_redirect(raiden_client.WEB_UI_INDEX_URL)
            except (RaidenClientError, RuntimeError) as exc:
                self._send_error_message(f"Raiden process failed to start: {exc}")
                raiden_client.kill()


class BaseRequestHandler(RequestHandler):
    def initialize(self, **kw):
        installer_settings_name = self.settings.get("installer_settings_name")
        self.installer_settings = available_settings[installer_settings_name]

    def render(self, template_name, **context_data):
        network = Network.get_by_name(self.installer_settings.network)
        required = RequiredAmounts.from_settings(self.installer_settings)
        context_data.update(
            {
                "network": network,
                "ethereum_required": required.eth,
                "ethereum_required_after_swap": required.eth_after_swap,
                "service_token_required": required.service_token,
                "transfer_token_required": required.transfer_token,
                "eip20_abi": json.dumps(EIP20_ABI),
            }
        )
        return super().render(template_name, **context_data)


class IndexHandler(BaseRequestHandler):
    def get(self):
        try:
            configuration_file = RaidenConfigurationFile.get_available_configurations().pop()
        except IndexError:
            configuration_file = None

        self.render("index.html", configuration_file=configuration_file)


class SetupHandler(BaseRequestHandler):
    def get(self, account_file):
        file_names = [os.path.basename(f) for f in RaidenConfigurationFile.list_existing_files()]
        self.render(
            "raiden_setup.html",
            configuration_file_names=file_names,
            network_name=self.installer_settings.network,
            account_file=account_file,
        )


class WalletCreationHandler(BaseRequestHandler):
    def get(self):
        self.render("account_password.html", network_name=self.installer_settings.network)


class AccountDetailHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        keystore_path = configuration_file.configuration_data["keystore-path"]
        filename = ""
        for file in glob(f"{keystore_path}/UTC--*"):
            file_path = Path(file)
            if file_path.is_file():
                keystore_content = json.loads(file_path.read_text())
                if (
                    to_checksum_address(keystore_content["address"])
                    == configuration_file.account.address
                ):
                    filename = os.path.basename(file)
                    break

        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )
        required = RequiredAmounts.from_settings(self.installer_settings)
        eth_balance = configuration_file.account.get_ethereum_balance(w3)
        log.info(f"Checking balance {eth_balance} > {required.eth}")
        if eth_balance < required.eth:
            log.info(f"funding tx {configuration_file._initial_funding_txhash}")
            if configuration_file._initial_funding_txhash is not None:
                return self.render(
                    "account.html", configuration_file=configuration_file, keystore=filename,
                )
        else:
            configuration_file._initial_funding_txhash = None
            configuration_file.save()

        if PASSPHRASE is not None:
            self.render("account.html", configuration_file=configuration_file, keystore=filename)
        else:
            self.render(
                "account_unlock.html",
                keystore_file_path=configuration_file.account.keystore_file_path,
                return_to=f"/account/{configuration_file_name}",
            )


class LaunchHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )

        current_balance = configuration_file.account.get_ethereum_balance(w3)

        if PASSPHRASE is not None:
            self.render(
                "launch.html", configuration_file=configuration_file, balance=current_balance
            )
        else:
            self.render(
                "account_unlock.html",
                keystore_file_path=configuration_file.account.keystore_file_path,
                return_to=f"/launch/{configuration_file_name}",
            )


class ConfigurationListHandler(BaseRequestHandler):
    def get(self):
        if not RaidenConfigurationFile.list_existing_files():
            raise HTTPError(404)

        self.render("configuration_list.html")


class APIHandler(RequestHandler):
    def set_default_headers(self, *args, **kw):
        self.set_header("Accept", "application/json")
        self.set_header("Content-Type", "application/json")

    def render_json(self, data):
        self.write(json.dumps(data))
        self.finish()


class ConfigurationListAPIHandler(APIHandler):
    def get(self):
        self.render_json(
            [
                self.reverse_url("api-configuration-detail", os.path.basename(f))
                for f in RaidenConfigurationFile.list_existing_files()
            ]
        )


class KeystoreHandler(APIHandler):
    def get(self, configuration_file_name, keystore_filename):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        keystore_path = configuration_file.configuration_data["keystore-path"]
        self.render(f"{keystore_path}/{keystore_filename}")


class GasPriceHandler(APIHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
        try_unlock(account)
        web3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        self.render_json(
            {
                "gas_price": web3.eth.generateGasPrice(),
                "block_number": web3.eth.blockNumber,
                "utc_seconds": int(time.time()),
            }
        )


class ConfigurationItemAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        network = configuration_file.network.name

        account = configuration_file.account

        try_unlock(account)
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)

        settings = available_settings[configuration_file.settings_name]
        required = RequiredAmounts.from_settings(settings)
        service_token = Erc20Token.find_by_ticker(required.service_token.ticker, network)
        transfer_token = Erc20Token.find_by_ticker(required.transfer_token.ticker, network)

        service_token_balance = get_total_token_owned(
            w3=w3, account=configuration_file.account, token=service_token
        )
        transfer_token_balance = get_token_balance(
            w3=w3, account=configuration_file.account, token=transfer_token
        )
        eth_balance = configuration_file.account.get_ethereum_balance(w3)

        def serialize_balance(balance_amount):
            return (
                {"as_wei": balance_amount.as_wei, "formatted": balance_amount.formatted}
                if balance_amount
                else None
            )

        self.render_json(
            {
                "url": self.reverse_url("api-configuration-detail", configuration_file.file_name),
                "file_name": configuration_file.file_name,
                "account_page_url": self.reverse_url("account", configuration_file.file_name),
                "account": configuration_file.account.address,
                "network": configuration_file.network.name,
                "balance": {
                    "ETH": serialize_balance(eth_balance),
                    "service_token": serialize_balance(service_token_balance),
                    "transfer_token": serialize_balance(transfer_token_balance),
                },
                "_initial_funding_txhash": configuration_file._initial_funding_txhash,
            }
        )
