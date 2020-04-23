import json
import os
import sys
import time
import webbrowser
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from ethtoken.abi import EIP20_ABI
from tornado.netutil import bind_sockets
from tornado.web import Application, HTTPError, HTTPServer, RequestHandler, url
from tornado.websocket import WebSocketHandler
from wtforms_tornado import Form

from raiden_installer import default_settings, get_resource_folder_path, log, network_settings
from raiden_installer.base import Account, RaidenConfigurationFile
from raiden_installer.ethereum_rpc import EthereumRPCProvider, Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.raiden import RaidenClient, RaidenClientError
from raiden_installer.token_exchange import Exchange, ExchangeError, Kyber, Uniswap
from raiden_installer.tokens import Erc20Token, EthereumAmount, RequiredAmounts, TokenAmount, Wei
from raiden_installer.transactions import (
    deposit_service_tokens,
    get_token_balance,
    get_token_deposit,
    get_total_token_owned,
    mint_tokens,
)
from raiden_installer.utils import check_eth_node_responsivity

DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ
PORT = 8080


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
    def _send_status_update(self, message_text):
        self.write_message(json.dumps({"type": "status-update", "text": message_text}))
        log.info(message_text)

    def _send_error_message(self, error_message):
        self.write_message(json.dumps({"type": "error-message", "text": error_message}))
        log.error(error_message)

    def _send_task_complete(self, message_text):
        self.write_message(json.dumps({"type": "task-complete", "text": message_text}))
        log.info(message_text)

    def _send_redirect(self, redirect_url):
        self.write_message(json.dumps({"type": "redirect", "redirect_url": redirect_url}))
        log.info(f"Redirecting to {redirect_url}")

    def on_message(self, message):
        data = json.loads(message)

        method = data.pop("method", None)
        action = method and {
            "close": self._run_close,
            "launch": self._run_launch,
            "setup": self._run_setup,
            "swap": self._run_swap,
            "track_transaction": self._run_track_transaction,
        }.get(method)

        return action and action(**data)

    def _run_close(self, **kw):
        sys.exit()

    def _run_funding(self, configuration_file: RaidenConfigurationFile):
        network = configuration_file.network
        settings = network_settings[network.name]

        if not network.FAUCET_AVAILABLE:
            self._send_error_message(
                f"Can not run automatic funding for {network.capitalized_name}"
            )
            return

        account = configuration_file.account
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        self._send_status_update(f"Obtaining {network.capitalized_name} ETH through faucet")
        network.fund(account)
        balance = account.wait_for_ethereum_funds(w3=w3, expected_amount=EthereumAmount(0.01))
        self._send_status_update(f"Account funded with {balance.formatted}")

        if settings.service_token.mintable:
            service_token = Erc20Token.find_by_ticker(
                settings.service_token.ticker, settings.network
            )
            self._send_status_update(f"Minting {service_token.ticker}")
            mint_tokens(w3, account, service_token)

        if settings.transfer_token.mintable:
            transfer_token = Erc20Token.find_by_ticker(
                settings.transfer_token.ticker, settings.network
            )
            self._send_status_update(f"Minting {transfer_token.ticker}")
            mint_tokens(w3, account, transfer_token)

    def _run_setup(self, **kw):
        form = QuickSetupForm(endpoint=kw.get("endpoint"), network=kw.get("network"))
        if form.validate():
            self._send_status_update("Generating new wallet and configuration file for raiden")

            network = Network.get_by_name(form.data["network"])
            url_or_infura_id = form.data["endpoint"].strip()

            if Infura.is_valid_project_id_or_endpoint(url_or_infura_id):
                ethereum_rpc_provider = Infura.make(network, url_or_infura_id)
            else:
                ethereum_rpc_provider = EthereumRPCProvider(url_or_infura_id)

            account = Account.create()

            try:
                check_eth_node_responsivity(ethereum_rpc_provider.url)
            except ValueError as e:
                self._send_error_message(f"Ethereum node unavailable: {e}.")
                return

            conf_file = RaidenConfigurationFile(
                account,
                network,
                ethereum_rpc_provider.url,
                routing_mode="pfs" if form.data["use_rsb"] else "local",
                enable_monitoring=form.data["use_rsb"],
            )
            conf_file.save()

            if network.FAUCET_AVAILABLE:
                self._run_funding(configuration_file=conf_file)
                self._send_redirect(self.reverse_url("launch", conf_file.file_name))
            else:
                self._send_redirect(self.reverse_url("account", conf_file.file_name))
        else:
            self._send_error_message(f"Failed to create account. Error: {form.errors}")

    def _run_launch(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        network_name = configuration_file.network.name
        raiden_client = RaidenClient.get_client(network_name)
        required = RequiredAmounts.for_network(network_name)

        if not raiden_client.is_installed:
            self._send_status_update(f"Downloading and installing raiden {raiden_client.release}")
            raiden_client.install()
            self._send_status_update("Installation complete")

        account = configuration_file.account
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
        service_token = Erc20Token.find_by_ticker(required.service_token.ticker, network_name)

        service_token_balance = get_token_balance(w3=w3, account=account, token=service_token)
        service_token_in_deposit = get_token_deposit(w3=w3, account=account, token=service_token)
        if service_token_balance.as_wei and service_token_in_deposit < required.service_token:
            self._send_status_update(
                f"Making deposit of {service_token_balance.formatted} for Raiden Services"
            )
            deposit_service_tokens(
                w3=w3, account=account, token=service_token, amount=service_token_balance.as_wei
            )
            service_token_deposited = get_token_deposit(
                w3=w3, account=account, token=service_token
            )
            self._send_status_update(
                f"Amount deposited at UDC: {service_token_deposited.formatted}"
            )

        self._send_status_update(
            "Launching Raiden, this might take a couple of minutes, do not close the browser"
        )

        if not raiden_client.is_running:
            raiden_client.launch(configuration_file)

        try:
            raiden_client.wait_for_web_ui_ready()
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
                w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
                token = Erc20Token.find_by_ticker(form.data["token_ticker"], network_name)

                token_amount = TokenAmount(Wei(form.data["token_amount"]), token)
                exchange = Exchange.get_by_name(form.data["exchange"])(w3=w3)
                self._send_status_update(f"Starting swap at {exchange.name}")

                costs = exchange.calculate_transaction_costs(token_amount, account)
                needed_funds = costs["total"]
                exchange_rate = costs["exchange_rate"]
                current_balance = account.get_ethereum_balance(w3)

                if needed_funds > current_balance:
                    raise ValueError(
                        (
                            f"Not enough ETH. {current_balance.formatted} available, but "
                            f"{needed_funds.formatted} needed"
                        )
                    )

                self._send_status_update(
                    (
                        f"Best exchange rate found at {exchange.name}: "
                        f"{exchange_rate.formatted} / {token_amount.ticker}"
                    )
                )
                self._send_status_update(
                    f"Trying to acquire up to {token_amount.formatted} at this rate"
                )
                self._send_status_update(f"Estimated costs: {needed_funds.formatted}")

                exchange.buy_tokens(account, token_amount)
                token_balance = get_token_balance(w3, account, token)

                self._send_status_update(f"Swap complete. {token_balance.formatted} available")
                self._send_redirect(self.reverse_url("launch", configuration_file.file_name))
            else:
                for key, error_list in form.errors.items():
                    error_message = f"{key}: {'/'.join(error_list)}"
                    self._send_error_message(error_message)
        except (json.decoder.JSONDecodeError, KeyError, ExchangeError, ValueError) as exc:
            self._send_error_message(str(exc))

    def _run_track_transaction(self, **kw):
        POLLING_INTERVAL = 10
        configuration_file_name = kw.get("configuration_file_name")
        tx_hash = kw.get("tx_hash")
        time_elapsed = 0

        try:
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
            account = configuration_file.account
            w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
            self._send_status_update(f"Waiting for confirmation of transaction {tx_hash}")

            while not w3.eth.getTransactionReceipt(tx_hash):
                time.sleep(POLLING_INTERVAL)
                time_elapsed += POLLING_INTERVAL

                self._send_status_update(f"Not confirmed after {time_elapsed} seconds...")
            self._send_status_update("Transaction confirmed")
            self._send_redirect(self.reverse_url("funding", configuration_file_name))
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


class SetupHandler(BaseRequestHandler):
    def get(self, network_name):
        file_names = [os.path.basename(f) for f in RaidenConfigurationFile.list_existing_files()]
        self.render(
            "raiden_setup.html", configuration_file_names=file_names, network_name=network_name
        )


class AccountDetailHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        self.render("account.html", configuration_file=configuration_file)


class AccountFundingHandler(BaseRequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        self.render("funding.html", configuration_file=configuration_file)


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

        self.render("launch.html", configuration_file=configuration_file, balance=current_balance)


class SwapOptionsHandler(BaseRequestHandler):
    def get(self, configuration_file_name, token_ticker):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )
        kyber = Kyber(w3=w3)
        uniswap = Uniswap(w3=w3)
        token = Erc20Token.find_by_ticker(token_ticker, configuration_file.network.name)

        self.render(
            "swap_options.html",
            configuration_file=configuration_file,
            kyber=kyber,
            uniswap=uniswap,
            token=token,
        )


class SwapHandler(BaseRequestHandler):
    def get(self, exchange_name, configuration_file_name, token_ticker):
        exchange_class = Exchange.get_by_name(exchange_name)
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )

        self.render(
            "swap.html",
            exchange=exchange_class(w3=w3),
            configuration_file=configuration_file,
            balance=configuration_file.account.get_ethereum_balance(w3),
            token=Erc20Token.find_by_ticker(token_ticker, configuration_file.network.name),
        )


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


class ConfigurationItemAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
        network = configuration_file.network.name
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
                "funding_page_url": self.reverse_url("funding", configuration_file.file_name),
                "account": configuration_file.account.address,
                "network": configuration_file.network.name,
                "balance": {
                    "ETH": serialize_balance(eth_balance),
                    "service_token": serialize_balance(service_token_balance),
                    "transfer_token": serialize_balance(transfer_token_balance),
                },
            }
        )


class CostEstimationAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        # Returns the highest estimate of ETH needed to get required service token amount
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        account = configuration_file.account
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


if __name__ == "__main__":
    log.info("Starting web server")
    app = Application(
        [
            url(r"/", IndexHandler, name="index"),
            url(r"/configurations", ConfigurationListHandler, name="configuration-list"),
            url(r"/setup/(mainnet|goerli)", SetupHandler, name="setup"),
            url(r"/account/(.*)", AccountDetailHandler, name="account"),
            url(r"/launch/(.*)", LaunchHandler, name="launch"),
            url(r"/funding/(.*)", AccountFundingHandler, name="funding"),
            url(r"/exchanges/(.*)/([A-Z]{3})", SwapOptionsHandler, name="swap-options"),
            url(r"/swap/(kyber|uniswap)/(.*)/([A-Z]{3})", SwapHandler, name="swap"),
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
        ],
        debug=DEBUG,
        static_path=os.path.join(RESOURCE_FOLDER_PATH, "static"),
        template_path=os.path.join(RESOURCE_FOLDER_PATH, "templates"),
    )

    sockets = bind_sockets((sum(ord(c) for c in "RAIDEN_WIZARD") + 1000) % 2 ** 16 - 1)
    server = HTTPServer(app)
    server.add_sockets(sockets)

    _, port = sockets[0].getsockname()
    local_url = f"http://localhost:{port}"
    log.info(f"Installer page ready on {local_url}")

    if not DEBUG:
        log.info("Should open automatically in browser...")
        webbrowser.open_new(local_url)

    tornado.ioloop.IOLoop.current().start()
