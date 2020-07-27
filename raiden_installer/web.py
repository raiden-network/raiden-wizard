import json
import os
import sys
import time
import webbrowser

import tornado.ioloop
import wtforms
from eth_utils import decode_hex
from tornado.escape import json_decode
from tornado.httputil import HTTPServerRequest
from tornado.netutil import bind_sockets
from tornado.web import Application, HTTPServer, url
from tornado.websocket import WebSocketHandler
from web3.exceptions import TimeExhausted
from wtforms_tornado import Form

from raiden_installer import get_resource_folder_path, log, network_settings
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.constants import WEB3_TIMEOUT
from raiden_installer.ethereum_rpc import make_web3_provider
from raiden_installer.network import Network
from raiden_installer.shared_handlers import (
    AccountDetailHandler,
    APIHandler,
    AsyncTaskHandler,
    BaseRequestHandler,
    ConfigurationItemAPIHandler,
    ConfigurationListAPIHandler,
    ConfigurationListHandler,
    GasPriceHandler,
    IndexHandler,
    KeystoreHandler,
    LaunchHandler,
    SetupHandler,
    WalletCreationHandler,
    try_unlock,
)
from raiden_installer.token_exchange import Exchange, ExchangeError, Kyber, Uniswap
from raiden_installer.tokens import (
    Erc20Token,
    EthereumAmount,
    RequiredAmounts,
    SwapAmounts,
    TokenAmount,
    Wei,
)
from raiden_installer.transactions import get_token_balance, get_total_token_owned
from raiden_installer.utils import recover_ld_library_env_path, wait_for_transaction

DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ

NETWORKS_WITH_TOKEN_SWAP = [Network.get_by_name(n) for n in ["mainnet", "ropsten", "goerli"]]

RESOURCE_FOLDER_PATH = get_resource_folder_path()


class TokenExchangeForm(Form):
    exchange = wtforms.SelectField(choices=[("kyber", "Kyber"), ("uniswap", "Uniswap")])
    network = wtforms.SelectField(
        choices=[(n.name, n.capitalized_name) for n in NETWORKS_WITH_TOKEN_SWAP]
    )
    token_ticker = wtforms.StringField()
    token_amount = wtforms.IntegerField()


class MainAsyncTaskHandler(AsyncTaskHandler):
    def __init__(
        self,
        application: Application,
        request: HTTPServerRequest,
        **kw
    ):
        super().__init__(application, request, **kw)
        self.actions.update({
            "swap": self._run_swap,
            "track_transaction": self._run_track_transaction,
        })

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
                    self._run_udc_deposit(w3, account, service_token, service_token_balance)

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


if __name__ == "__main__":
    log.info("Starting web server")
    app = Application(
        [
            url(r"/", IndexHandler, name="index"),
            url(r"/configurations", ConfigurationListHandler, name="configuration-list"),
            url(r"/setup/mainnet/(.*)", SetupHandler, name="setup"),
            url(r"/create_wallet/mainnet", WalletCreationHandler, name="create_wallet"),
            url(r"/account/(.*)", AccountDetailHandler, name="account"),
            url(r"/keystore/(.*)/(.*)", KeystoreHandler, name="keystore"),
            url(r"/launch/(.*)", LaunchHandler, name="launch"),
            url(r"/swap/(.*)/([A-Z]{3})", SwapHandler, name="swap"),
            url(r"/ws", MainAsyncTaskHandler, name="websocket"),
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
