import json
import os
import sys
import time
import webbrowser
from glob import glob
from pathlib import Path
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from eth_utils import decode_hex, to_checksum_address
from tornado.escape import json_decode
from tornado.netutil import bind_sockets
from tornado.web import Application, HTTPError, HTTPServer, RequestHandler, url
from tornado.websocket import WebSocketHandler
from web3.exceptions import TimeExhausted
from wtforms.validators import EqualTo
from wtforms_tornado import Form

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_installer import default_settings, get_resource_folder_path, log, network_settings
from raiden_installer.base import Account, RaidenConfigurationFile
from raiden_installer.constants import WEB3_TIMEOUT
from raiden_installer.ethereum_rpc import EthereumRPCProvider, Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.raiden import RaidenClient, RaidenClientError, temporary_passphrase_file
from raiden_installer.token_exchange import Exchange, ExchangeError, Kyber, Uniswap
from raiden_installer.tokens import (
    Erc20Token,
    EthereumAmount,
    RequiredAmounts,
    SwapAmounts,
    TokenAmount,
    Wei,
)
from raiden_installer.transactions import (
    deposit_service_tokens,
    get_token_balance,
    get_token_deposit,
    get_total_token_owned,
    mint_tokens,
)
from raiden_installer.utils import (
    check_eth_node_responsivity,
    recover_ld_library_env_path,
    wait_for_transaction,
)

EIP20_ABI = ContractManager(contracts_precompiled_path()).get_contract_abi("StandardToken")
DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ
PORT = 8080
PASSPHRASE = None


AVAILABLE_NETWORKS = [Network.get_by_name(n) for n in ["mainnet", "ropsten", "goerli"]]
NETWORKS_WITH_TOKEN_SWAP = [Network.get_by_name(n) for n in ["mainnet", "ropsten", "goerli"]]
DEFAULT_NETWORK = Network.get_default()

RESOURCE_FOLDER_PATH = get_resource_folder_path()


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


class TokenExchangeForm(Form):
    exchange = wtforms.SelectField(choices=[("kyber", "Kyber"), ("uniswap", "Uniswap")])
    network = wtforms.SelectField(
        choices=[(n.name, n.capitalized_name) for n in NETWORKS_WITH_TOKEN_SWAP]
    )
    token_ticker = wtforms.StringField()
    token_amount = wtforms.IntegerField()


class FundingOptionsForm(Form):
    funding_option = wtforms.RadioField(
        choices=[
            ("no-action", "User will deposit RDN"),
            ("run-swap", "Wizard will swap ETH <-> RDN"),
        ]
    )


class AsyncTaskHandler(WebSocketHandler):
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

    def _send_next_step(self, message_text, title, step):
        if not isinstance(message_text, list):
            message_text = [message_text]
        body = {"type": "next-step", "text": message_text, "title": title, "step": step}
        self.write_message(json.dumps(body))
        log.info(" ".join(message_text))
        log.info(f"Update progress to step {step}: {title}")

    def on_message(self, message):
        data = json.loads(message)

        method = data.pop("method", None)
        action = method and {
            "close": self._run_close,
            "launch": self._run_launch,
            "setup": self._run_setup,
            "unlock": self._run_unlock,
            "create_wallet": self._run_create_wallet,
            "swap": self._run_swap,
            "track_transaction": self._run_track_transaction,
            "fund": self._run_funding,
        }.get(method)

        return action and action(**data)

    def _run_close(self, **kw):
        sys.exit()

    def _run_funding(self, **kw):
        try:
            configuration_file_name = kw.get("configuration_file_name")
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        except Exception as exc:
            self._send_error_message(str(exc))
            return

        network = configuration_file.network
        settings = network_settings[network.name]

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

        if settings.service_token.mintable:
            service_token = Erc20Token.find_by_ticker(
                settings.service_token.ticker, settings.network
            )
            self._send_next_step(
                f"Minting {service_token.ticker}",
                f"Fund Account with {service_token.ticker}",
                3,
            )
            transaction_receipt = mint_tokens(w3, account, service_token)
            wait_for_transaction(w3, transaction_receipt)

        if settings.transfer_token.mintable:
            transfer_token = Erc20Token.find_by_ticker(
                settings.transfer_token.ticker, settings.network
            )
            self._send_next_step(
                f"Minting {transfer_token.ticker}",
                f"Fund Account with {transfer_token.ticker}",
                4,
            )
            transaction_receipt = mint_tokens(w3, account, transfer_token)
            wait_for_transaction(w3, transaction_receipt)

        self._send_redirect(self.reverse_url("launch", configuration_file_name))

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
                self.reverse_url("setup", network_name, account.keystore_file_path)
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
                network,
                ethereum_rpc_provider.url,
                routing_mode="pfs" if form.data["use_rsb"] else "local",
                enable_monitoring=form.data["use_rsb"],
            )
            conf_file.save()
            
            self._send_redirect(self.reverse_url("account", conf_file.file_name))

            # if network.FAUCET_AVAILABLE:
            #     self._run_funding(configuration_file=conf_file)
            #     self._send_redirect(self.reverse_url("launch", conf_file.file_name))#todo
            # else:
        else:
            self._send_error_message(f"Failed to create account. Error: {form.errors}")

    def _run_launch(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        network_name = configuration_file.network.name
        raiden_client = RaidenClient.get_client(network_name)

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

    def _run_swap(self, **kw):
        try:
            configuration_file_name = kw.get("configuration_file_name")
            exchange_name = kw["exchange"]
            token_amount = kw["amount"]
            token_ticker = kw["token"]
        except (ValueError, KeyError, TypeError) as exc:
            self._send_error_message(f"Invalid request: {exc}")
            return

        try:
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
            network_name = configuration_file.network.name
            form = TokenExchangeForm(
                {
                    "network": [network_name],
                    "exchange": [exchange_name],
                    "token_amount": [token_amount],
                    "token_ticker": [token_ticker],
                }
            )

            if form.validate():
                account = configuration_file.account
                try_unlock(account)
                w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
                token = Erc20Token.find_by_ticker(form.data["token_ticker"], network_name)

                token_amount = TokenAmount(Wei(form.data["token_amount"]), token)
                exchange = Exchange.get_by_name(form.data["exchange"])(w3=w3)
                self._send_status_update(f"Starting swap at {exchange.name}")

                costs = exchange.calculate_transaction_costs(token_amount, account)
                needed_funds = costs["total"]
                exchange_rate = costs["exchange_rate"]
                balance_before_swap = account.get_ethereum_balance(w3)

                if needed_funds > balance_before_swap:
                    raise ValueError(
                        (
                            f"Not enough ETH. {balance_before_swap.formatted} available, but "
                            f"{needed_funds.formatted} needed"
                        )
                    )

                self._send_status_update(
                    (
                        f"Best exchange rate found at {exchange.name}: "
                        f"{exchange_rate} / {token_amount.ticker}"
                    )
                )
                self._send_status_update(f"Trying to acquire {token_amount} at this rate")

                transaction_receipt = exchange.buy_tokens(account, token_amount, costs)
                wait_for_transaction(w3, transaction_receipt)

                token_balance = get_token_balance(w3, account, token)
                balance_after_swap = account.get_ethereum_balance(w3)
                actual_total_costs = balance_before_swap - balance_after_swap

                self._send_status_update(f"Swap complete. {token_balance.formatted} available")
                self._send_status_update(f"Actual costs: {actual_total_costs}")

                required = RequiredAmounts.for_network(network_name)
                service_token = Erc20Token.find_by_ticker(
                    required.service_token.ticker, network_name
                )
                service_token_balance = get_token_balance(w3, account, service_token)
                total_service_token_balance = get_total_token_owned(w3, account, service_token)
                transfer_token = Erc20Token.find_by_ticker(
                    required.transfer_token.ticker, network_name
                )
                transfer_token_balance = get_token_balance(w3, account, transfer_token)

                if total_service_token_balance < required.service_token:
                    raise ExchangeError("Exchange was not successful")

                elif service_token_balance.as_wei > 0:

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

                if transfer_token_balance < required.transfer_token:
                    redirect_url = self.reverse_url(
                        "swap", configuration_file.file_name, transfer_token.ticker
                    )
                    next_page = "Moving on to exchanging DAI ..."

                else:
                    redirect_url = self.reverse_url("launch", configuration_file.file_name)
                    next_page = "You are ready to launch Raiden! ..."

                self._send_summary(
                    ["Congratulations! Swap Successful!", next_page], icon=token_ticker
                )
                time.sleep(5)
                self._send_redirect(redirect_url)
            else:
                for key, error_list in form.errors.items():
                    error_message = f"{key}: {'/'.join(error_list)}"
                    self._send_error_message(error_message)
        except (json.decoder.JSONDecodeError, KeyError, ExchangeError, ValueError) as exc:
            self._send_error_message(str(exc))
            redirect_url = self.reverse_url("swap", configuration_file.file_name, token_ticker)
            next_page = f"Try again to exchange {token_ticker}..."
            self._send_summary(["Transaction failed", str(exc), next_page], icon="error")
            time.sleep(5)
            self._send_redirect(redirect_url)

    def _run_track_transaction(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        tx_hash = kw.get("tx_hash")
        time_start = time.time()
        try:
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
            configuration_file._initial_funding_txhash = tx_hash
            configuration_file.save()
            account = configuration_file.account
            w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
            self._send_txhash_message(["Waiting for confirmation of transaction"], tx_hash=tx_hash)

            transaction_found = False

            while (not transaction_found) and (time.time() - time_start < WEB3_TIMEOUT):
                try:
                    tx_receipt = w3.eth.waitForTransactionReceipt(
                        decode_hex(tx_hash), timeout=WEB3_TIMEOUT
                    )
                    assert tx_receipt.get("blockNumber", 0) > 0
                    transaction_found = True
                except TimeExhausted:
                    pass

            if not transaction_found:
                self._send_status_update(
                    [f"Not confirmed after {int(time.time() - time_start)} seconds!"], icon="error"
                )
                self._send_txhash_message(
                    "Funding took too long! "
                    "Click the link below and restart the wizard, "
                    "once it was confirmed:",
                    tx_hash=tx_hash,
                )
                time.sleep(10)
                sys.exit(1)

            else:
                configuration_file._initial_funding_txhash = None
                configuration_file.save()

            self._send_status_update("Transaction confirmed")
            service_token = configuration_file.settings.service_token
            self._send_redirect(
                self.reverse_url("swap", configuration_file.file_name, service_token.ticker)
            )
        except Exception as exc:
            self._send_error_message(str(exc))


class BaseRequestHandler(RequestHandler):
    def render(self, template_name, **context_data):
        configuration_file = context_data.get("configuration_file")
        if configuration_file:
            network = configuration_file.network
        else:
            network = Network.get_by_name(default_settings.network)
        required = RequiredAmounts.for_network(network.name)
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


class ConfigurationListHandler(BaseRequestHandler):
    def get(self):
        if not RaidenConfigurationFile.list_existing_files():
            raise HTTPError(404)

        self.render("configuration_list.html")


class WalletCreationHandler(BaseRequestHandler):
    def get(self, network_name):
        self.render("account_password.html", network_name=network_name)


class SetupHandler(BaseRequestHandler):
    def get(self, network_name, account_file):
        file_names = [os.path.basename(f) for f in RaidenConfigurationFile.list_existing_files()]
        self.render(
            "raiden_setup.html",
            configuration_file_names=file_names,
            network_name=network_name,
            account_file=account_file,
        )


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
        required = RequiredAmounts.for_network(configuration_file.network.name)
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


class FundingOptionsHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        self.render("funding_select_method.html", configuration_file=configuration_file)

    def post(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        form = FundingOptionsForm(self.request.arguments)
        if form.validate():
            next_view = {"no-action": "launch", "run-swap": "swap-options"}[
                form.data["funding_option"]
            ]
            return self.redirect(self.reverse_url(next_view, configuration_file.file_name))
        else:
            self.render("funding_select_method.html", configuration_file=configuration_file)


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


class SwapHandler(BaseRequestHandler):
    def get(self, configuration_file_name, token_ticker):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )
        kyber = Kyber(w3=w3)
        uniswap = Uniswap(w3=w3)
        token = Erc20Token.find_by_ticker(token_ticker, configuration_file.network.name)

        network = configuration_file.network
        settings = network_settings[network.name]
        swap_amounts = SwapAmounts.from_settings(settings)
        if token_ticker == settings.service_token.ticker:
            swap_amount_1 = swap_amounts.service_token_1
            swap_amount_2 = swap_amounts.service_token_2
            swap_amount_3 = swap_amounts.service_token_3
        elif token_ticker == settings.transfer_token.ticker:
            swap_amount_1 = swap_amounts.transfer_token_1
            swap_amount_2 = swap_amounts.transfer_token_2
            swap_amount_3 = swap_amounts.transfer_token_3

        self.render(
            "swap.html",
            configuration_file=configuration_file,
            kyber=kyber,
            uniswap=uniswap,
            token=token,
            swap_amount_1=swap_amount_1,
            swap_amount_2=swap_amount_2,
            swap_amount_3=swap_amount_3,
        )


class APIHandler(RequestHandler):
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


class ConfigurationListAPIHandler(APIHandler):
    def get(self):
        self.render_json(
            [
                self.reverse_url("api-configuration-detail", os.path.basename(f))
                for f in RaidenConfigurationFile.list_existing_files()
            ]
        )


class ConfigurationItemAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        network = configuration_file.network.name

        account = configuration_file.account

        try_unlock(account)
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)

        required = RequiredAmounts.for_network(network)
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


def try_unlock(account):
    if account.check_passphrase(PASSPHRASE):
        account.passphrase = PASSPHRASE


class CostEstimationAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        # Returns the highest estimate of ETH needed to get required service token amount
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
        try_unlock(account)
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        required = RequiredAmounts.for_network(configuration_file.network.name)

        kyber = Kyber(w3=w3)
        uniswap = Uniswap(w3=w3)

        highest_cost = 0
        for exchange in (kyber, uniswap):
            exchange_costs = exchange.calculate_transaction_costs(required.service_token, account)
            if not exchange_costs:
                continue
            total_cost = exchange_costs["total"].as_wei
            highest_cost = max(highest_cost, total_cost)

        estimated_cost = EthereumAmount(Wei(highest_cost))
        self.render_json(
            {
                "dex_swap_RDN": {
                    "as_wei": estimated_cost.as_wei,
                    "formatted": estimated_cost.formatted,
                }
            }
        )

    def post(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
        try_unlock(account)
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        ex_currency_amt = json_decode(self.request.body)
        exchange = Exchange.get_by_name(ex_currency_amt["exchange"])(w3=w3)
        currency = Erc20Token.find_by_ticker(
            ex_currency_amt["currency"], configuration_file.network
        )
        token_amount = TokenAmount(ex_currency_amt["target_amount"], currency)
        try:
            exchange_costs = exchange.calculate_transaction_costs(token_amount, account)
            total_cost = exchange_costs["total"]
            self.render_json(
                {
                    "exchange": exchange.name,
                    "currency": currency.ticker,
                    "target_amount": ex_currency_amt["target_amount"],
                    "as_wei": total_cost.as_wei,
                    "formatted": total_cost.formatted,
                    "utc_seconds": int(time.time()),
                }
            )
        except ExchangeError as ex:
            log.error("There was an error preparing the exchange", exc_info=ex)
            self.set_status(
                status_code=409,
                reason=str(ex),
            )


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


if __name__ == "__main__":
    log.info("Starting web server")
    app = Application(
        [
            url(r"/", IndexHandler, name="index"),
            url(r"/configurations", ConfigurationListHandler, name="configuration-list"),
            url(r"/setup/(mainnet|goerli)/(.*)", SetupHandler, name="setup"),
            url(r"/create_wallet/(mainnet|goerli)", WalletCreationHandler, name="create_wallet"),
            url(r"/account/(.*)", AccountDetailHandler, name="account"),
            url(r"/keystore/(.*)/(.*)", KeystoreHandler, name="keystore"),
            url(r"/launch/(.*)", LaunchHandler, name="launch"),
            url(r"/swap/(.*)/([A-Z]{3})", SwapHandler, name="swap"),
            url(r"/ws", AsyncTaskHandler, name="websocket"),
            url(r"/api/cost-estimation/(.*)", CostEstimationAPIHandler, name="api-cost-detail"),
            url(
                r"/api/configurations", ConfigurationListAPIHandler, name="api-configuration-list"
            ),
            url(
                r"/api/configuration/(.*)",
                ConfigurationItemAPIHandler,
                name="api-configuration-detail",
            ),
            url(r"/gas_price/(.*)", GasPriceHandler, name="gas_price"),
        ],
        debug=DEBUG,
        static_path=os.path.join(RESOURCE_FOLDER_PATH, "static"),
        template_path=os.path.join(RESOURCE_FOLDER_PATH, "templates"),
    )

    # port = (sum(ord(c) for c in "RAIDEN_WIZARD") + 1000) % 2 ** 16 - 1 = 1994
    sockets = bind_sockets(1994, "localhost")
    server = HTTPServer(app)
    server.add_sockets(sockets)

    _, port = sockets[0].getsockname()
    local_url = f"http://localhost:{port}"
    log.info(f"Installer page ready on {local_url}")

    if not DEBUG:
        log.info("Should open automatically in browser...")
        recover_ld_library_env_path()
        webbrowser.open_new(local_url)

    tornado.ioloop.IOLoop.current().start()
