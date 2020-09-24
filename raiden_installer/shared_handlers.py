import json
import os
import sys
import time
import webbrowser
from glob import glob
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from eth_utils import to_checksum_address
from tornado.netutil import bind_sockets
from tornado.web import Application, HTTPError, HTTPServer, RequestHandler, url
from tornado.websocket import WebSocketHandler
from wtforms.validators import EqualTo
from wtforms_tornado import Form

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_installer import get_resource_folder_path, load_settings, log
from raiden_installer.account import Account, find_keystore_folder_path
from raiden_installer.base import RaidenConfigurationFile
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
from raiden_installer.utils import (
    check_eth_node_responsivity,
    recover_ld_library_env_path,
    wait_for_transaction,
)

DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ

RESOURCE_FOLDER_PATH = get_resource_folder_path()

EIP20_ABI = ContractManager(contracts_precompiled_path()).get_contract_abi("StandardToken")
AVAILABLE_NETWORKS = [Network.get_by_name(n) for n in ["mainnet", "goerli"]]

PASSPHRASE: Optional[str] = None


def get_passphrase() -> Optional[str]:
    return PASSPHRASE


def set_passphrase(passphrase: Optional[str]):
    global PASSPHRASE
    PASSPHRASE = passphrase


def try_unlock(account):
    passphrase = get_passphrase()
    if account.check_passphrase(passphrase):
        account.passphrase = passphrase


class QuickSetupForm(Form):
    network = wtforms.HiddenField("Network")
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
        self.installer_settings = self.settings.get("installer_settings")
        self.actions = {
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

    def _deposit_to_udc(self, w3, account, service_token, deposit_amount):
        self._send_status_update(
            f"Making deposit of {deposit_amount.formatted} to the "
            "User Deposit Contract"
        )
        self._send_status_update(f"This might take a few minutes")
        tx_hash = deposit_service_tokens(
            w3=w3,
            account=account,
            token=service_token,
            amount=deposit_amount.as_wei,
        )
        wait_for_transaction(w3, tx_hash)
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
            set_passphrase(passphrase)
            self._send_redirect(kw.get("return_to"))
        else:
            self._send_error_message("Incorrect passphrase, try again.")

    def _run_create_wallet(self, **kw):
        form = PasswordForm(passphrase1=kw.get("passphrase1"), passphrase2=kw.get("passphrase2"))
        if form.validate():
            self._send_status_update("Generating new wallet file for Raiden")
            passphrase = form.data["passphrase1"].strip()
            set_passphrase(passphrase)
            account = Account.create(find_keystore_folder_path(), passphrase)

            self._send_redirect(
                self.reverse_url("setup", account.keystore_file_path)
            )

    def _run_setup(self, **kw):
        account_file = kw.get("account_file")
        account = Account(account_file, passphrase=get_passphrase())
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
                self.installer_settings,
                ethereum_rpc_provider.url,
                routing_mode=self.installer_settings.routing_mode,
                enable_monitoring=self.installer_settings.monitoring_enabled,
            )
            conf_file.save()

            self._send_redirect(self.reverse_url("account", conf_file.file_name))
        else:
            self._send_error_message(f"Failed to create account. Error: {form.errors}")

    def _run_launch(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
        try_unlock(account)
        if account.passphrase is None:
            self._send_error_message("Failed to unlock account! Please reload page")
            return

        raiden_client = RaidenClient.get_client(self.installer_settings)
        if not raiden_client.is_installed:
            self._send_status_update(f"Downloading and installing raiden {raiden_client.release}")
            raiden_client.install()
            self._send_status_update("Installation complete")

        self._send_status_update(
            "Launching Raiden, this might take a couple of minutes, do not close the browser"
        )

        with temporary_passphrase_file(get_passphrase()) as passphrase_file:
            if not raiden_client.is_running:
                raiden_client.launch(configuration_file, passphrase_file)

            try:
                raiden_client.wait_for_web_ui_ready(
                    status_callback=lambda stat: log.info(str(stat))
                )
                self._send_task_complete("Raiden is ready!")
                self._send_redirect(RaidenClient.WEB_UI_INDEX_URL)
            except (RaidenClientError, RuntimeError) as exc:
                self._send_error_message(f"Raiden process failed to start: {exc}")
                raiden_client.kill()


class BaseRequestHandler(RequestHandler):
    def initialize(self):
        self.installer_settings = self.settings.get("installer_settings")

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
            configuration_file = RaidenConfigurationFile.get_available_configurations(
                self.installer_settings
            ).pop()
        except IndexError:
            configuration_file = None

        self.render("index.html", configuration_file=configuration_file)


class SetupHandler(BaseRequestHandler):
    def get(self, account_file):
        self.render("raiden_setup.html", account_file=account_file)


class WalletCreationHandler(BaseRequestHandler):
    def get(self):
        self.render("account_password.html")


class AccountDetailHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        if get_passphrase() is None:
            self.render(
                "account_unlock.html",
                keystore_file_path=configuration_file.account.keystore_file_path,
                return_to=f"/account/{configuration_file_name}",
            )
            return

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
        log.info(f"funding tx {configuration_file._initial_funding_txhash}")
        log.info(f"Checking balance {eth_balance} >= {required.eth}")
        if eth_balance >= required.eth:
            configuration_file._initial_funding_txhash = None
            configuration_file.save()

        self.render("account.html", configuration_file=configuration_file, keystore=filename)


class LaunchHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        if get_passphrase() is None:
            self.render(
                "account_unlock.html",
                keystore_file_path=configuration_file.account.keystore_file_path,
                return_to=f"/launch/{configuration_file_name}",
            )
            return

        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )
        current_balance = configuration_file.account.get_ethereum_balance(w3)

        self.render(
            "launch.html", configuration_file=configuration_file, balance=current_balance
        )


class APIHandler(RequestHandler):
    def initialize(self):
        self.installer_settings = self.settings.get("installer_settings")

    def set_default_headers(self, *args, **kw):
        self.set_header("Accept", "application/json")
        self.set_header("Content-Type", "application/json")

    def render_json(self, data):
        self.write(json.dumps(data))
        self.finish()


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

        settings = configuration_file.settings
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
                "file_name": configuration_file.file_name,
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


def create_app(settings_name: str, additional_handlers: list) -> Application:
    log.info("Starting web server")

    handlers = [
        url(r"/", IndexHandler, name="index"),
        url(r"/setup/(.*)", SetupHandler, name="setup"),
        url(r"/create_wallet", WalletCreationHandler, name="create_wallet"),
        url(r"/account/(.*)", AccountDetailHandler, name="account"),
        url(r"/keystore/(.*)/(.*)", KeystoreHandler, name="keystore"),
        url(r"/launch/(.*)", LaunchHandler, name="launch"),
        url(r"/gas_price/(.*)", GasPriceHandler, name="gas_price"),
        url(
            r"/api/configuration/(.*)",
            ConfigurationItemAPIHandler,
            name="api-configuration-detail",
        ),
    ]

    settings = load_settings(settings_name)

    return Application(
        handlers + additional_handlers,
        debug=DEBUG,
        static_path=os.path.join(RESOURCE_FOLDER_PATH, "static"),
        template_path=os.path.join(RESOURCE_FOLDER_PATH, "templates"),
        installer_settings=settings
    )


def run_server(app: Application, port: int):  # pragma: no cover
    sockets = bind_sockets(port, "localhost")
    server = HTTPServer(app)
    server.add_sockets(sockets)

    _, socket_port = sockets[0].getsockname()
    local_url = f"http://localhost:{socket_port}"
    log.info(f"Installer page ready on {local_url}")

    if not DEBUG:
        log.info("Should open automatically in browser...")
        recover_ld_library_env_path()
        webbrowser.open_new(local_url)

    tornado.ioloop.IOLoop.current().start()
