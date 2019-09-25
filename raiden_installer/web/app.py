import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from tornado.web import Application, RequestHandler, url
from tornado.websocket import WebSocketHandler
from wtforms_tornado import Form

from .. import log
from ..base import Account, RaidenConfigurationFile
from ..network import Network
from ..raiden import RaidenClient, RaidenClientError
from ..ethereum_rpc import Infura, EthereumRPCProvider, make_web3_provider
from ..tokens import EthereumAmount, RDNAmount, DAIAmount, Wei
from ..token_exchange import Exchange, Kyber, Uniswap


DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ
PORT = 8080


FUNDING_AMOUNTS = [75, 100, 150, 200, 500, 1000]
AVAILABLE_NETWORKS = [Network.get_by_name(n) for n in ["mainnet", "ropsten", "goerli"]]
NETWORKS_WITH_TOKEN_SWAP = [Network.get_by_name(n) for n in ["mainnet", "ropsten"]]


def get_data_folder_path():
    # Find absolute path for non-code resources (static files, templates) When
    # we are running in development, it will just be the same folder as this
    # file, but when bundled by pyinstaller, it will be placed on the folder
    # indicated by sys._MEIPASS
    return getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)


class QuickSetupForm(Form):
    network = wtforms.HiddenField("Network", default="mainnet")
    use_rsb = wtforms.HiddenField("Use Raiden Service Bundle", default=True)
    endpoint = wtforms.StringField("Infura Project ID/RPC Endpoint")

    def validate_network(self, field):
        network_name = field.data
        if network_name not in [n.name for n in AVAILABLE_NETWORKS]:
            raise wtforms.ValidationError(f"Can not run quick setup raiden with {network_name}")

    def validate_endpoint(self, field):
        data = field.data.strip()
        parsed_url = urlparse(data)
        is_valid_url = bool(parsed_url.scheme) and bool(parsed_url.netloc)
        is_valid_project_id = Infura.is_valid_project_id(data)

        if not (is_valid_project_id or is_valid_url):
            raise wtforms.ValidationError("Not a valid URL nor Infura Project ID")


class TokenExchangeForm(Form):
    exchange = wtforms.SelectField(choices=[("kyber", "Kyber"), ("uniswap", "Uniswap")])
    network = wtforms.SelectField(
        choices=[(n.name, n.capitalized_name) for n in NETWORKS_WITH_TOKEN_SWAP]
    )
    token_sticker = wtforms.SelectField(
        choices=[(RDNAmount.STICKER, RDNAmount.STICKER), (DAIAmount.STICKER, DAIAmount.STICKER)]
    )
    token_amount = wtforms.IntegerField()


class AsyncTaskHandler(WebSocketHandler):
    def _send_status_update(self, message_text, message_type="info", complete=False):
        self.write_message(
            json.dumps({"type": "status-update", "text": message_text, "complete": complete})
        )
        log.info(message_text)


class ExchangeRateTrackerHandler(AsyncTaskHandler):
    def _serialize_quote(self, exchange, token_amount, account):
        costs = exchange.calculate_transaction_costs(token_amount, account)
        total_price = costs and costs.get("total")

        return total_price and {"wei": total_price.as_wei, "formatted": total_price.formatted}

    def open(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )

        kyber = Kyber(w3=w3)
        uniswap = Uniswap(w3=w3)

        is_kyber_listing = kyber.is_listing_token("RDN")
        is_uniswap_listing = uniswap.is_listing_token("RDN")

        for amount in FUNDING_AMOUNTS:
            rdn_amount = RDNAmount(amount)
            data = {"type": "new-quote", "token_amount": str(rdn_amount.as_wei)}

            if is_kyber_listing:
                data["kyber_price"] = self._serialize_quote(
                    kyber, rdn_amount, configuration_file.account
                )

            if is_uniswap_listing:
                data["uniswap_price"] = self._serialize_quote(
                    uniswap, rdn_amount, configuration_file.account
                )

            self.write_message(json.dumps(data))


class SwapStatusNotificationHandler(AsyncTaskHandler):
    def on_message(self, message):
        DEPOSIT_TIMEOUT = 5
        try:
            data = json.loads(message)
            configuration_file = RaidenConfigurationFile.get_by_filename(
                data["configuration_file_name"]
            )
            form = TokenExchangeForm(
                {
                    "network": [configuration_file.network.name],
                    "exchange": [data["exchange"]],
                    "token_amount": [data["amount"]],
                    "token_sticker": [data["token"]],
                }
            )

            if form.validate():
                account = configuration_file.account
                w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
                rdn_amount = RDNAmount(Wei(form.data["token_amount"]))
                exchange = Exchange.get_by_name(form.data["exchange"])(w3=w3)

                self._send_status_update("")
                costs = exchange.calculate_transaction_costs(rdn_amount, account)
                needed_funds = costs["total"]
                current_balance = account.get_ethereum_balance(w3)
                required_deposit_amount = EthereumAmount(
                    Wei(current_balance.as_wei - needed_funds.as_wei)
                )

                if required_deposit_amount.as_wei > 0:
                    self._send_status_update(
                        f"Please deposit at least {required_deposit_amount.formatted} to "
                        f"{account.address} in the next {DEPOSIT_TIMEOUT} minutes"
                    )
                balance = account.wait_for_ethereum_funds(
                    w3, required_deposit_amount, timeout=DEPOSIT_TIMEOUT * 60
                )
                self._send_status_update(f"Account balance now is {balance.formatted}")
                self._send_status_update(f"Executing ETH <-> RDN swap on {exchange.name}")
                exchange.buy_tokens(account, rdn_amount)
                self._send_status_update(f"Swap complete. {rdn_amount.balance} available")

            else:
                for key, error_list in form.errors.items():
                    error_message = f"{key}: {'/'.join(error_list)}"
                    self._send_status_update(message_type="error", message_text=error_message)
        except (json.decoder.JSONDecodeError, KeyError) as exc:
            self._send_status_update(message_type="error", message_text=str(exc))


class LauncherStatusNotificationHandler(AsyncTaskHandler):
    def open(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)

        account = configuration_file.account
        network = configuration_file.network
        # w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)

        # raiden_token = RaidenTokenNetwork(w3=w3, account=account)
        # custom_token = CustomTokenNetwork(w3=w3, account=account)

        # ethereum_amount = network.MINIMUM_ETHEREUM_BALANCE_REQUIRED

        # has_faucet = network.FAUCET_AVAILABLE
        # needed_funds = ethereum_amount - account.get_ethereum_balance(w3)
        # needs_funding = any(
        #     [
        #         raiden_token.is_available(network) and not raiden_token.is_funded,
        #         custom_token.is_available(network) and not custom_token.is_funded,
        #     ]
        # )

        # try:
        #     if needs_funding and needed_funds <= 0:
        #         self._send_status_update(f"Account is funded with enough ETH to swap for tokens")
        #     elif needs_funding and needed_funds > 0 and has_faucet:
        #         self._send_status_update(f"Funding account with {network.capitalized_name} ETH")
        #         network.fund(account)
        #         self._send_status_update(f"ETH successfully acquired", message_type="success")
        #     elif needs_funding:
        #         self._send_status_update(
        #             f"Please send at least {needed_funds:0.4f} ETH to 0x{account.address} on "
        #             f"{network.capitalized_name}"
        #         )
        #         account.wait_for_ethereum_funds(w3, network)
        #     else:
        #         self._send_status_update(f"ETH funding not required at the moment")
        #     self._send_status_update(
        #         f"Current balance: {account.get_ethereum_balance(w3):0.4f} ETH"
        #     )
        # except Exception as exc:
        #     self._send_status_update(
        #         f"Failed to add funds to account: {exc}", message_type="warning"
        #     )

        # if custom_token.is_available(network):
        #     if not custom_token.is_funded:
        #         try:
        #             self._send_status_update(f"Obtaining tokens")
        #             custom_token.mint(CustomTokenNetwork.TOKEN_AMOUNT)
        #             custom_token.deposit(CustomTokenNetwork.TOKEN_AMOUNT)
        #             self._send_status_update(
        #                 "Raiden successfully funded with tokens", message_type="success"
        #             )
        #         except Exception as exc:
        #             self._send_status_update(
        #                 f"Failed to pre-mint custom tokens.", message_type="error"
        #             )
        #             self._send_status_update(
        #                 f"You should still be able to do it on Raiden Web UI: {exc}",
        #                 message_type="error",
        #             )
        #     else:
        #         self._send_status_update(
        #             f"Account already funded with {custom_token.balance:0.4f} WIZ"
        #         )

        # if raiden_token.is_available(network):
        #     if not raiden_token.is_funded:
        #         try:
        #             self._send_status_update(f"Running ETH <-> RDN Swap")
        #             exchange = Exchange.select_by_rate(w3, account, ethereum_amount)
        #             exchange_rate = exchange.get_current_rate(ethereum_amount)
        #             self._send_status_update(
        #                 f"{exchange.name} has the best rate of {exchange_rate:0.4f} RDN/ETH"
        #             )
        #             exchange.swap_ethereum_for_rdn(ethereum_amount, exchange_rate)
        #         except ExchangeError as exc:
        #             self._send_status_update(
        #                 f"Failed to exchange ETH for RDN: {exc}", message_type="error"
        #             )
        #     else:
        #         self._send_status_update(f"Account has already {raiden_token.balance:0.4f} RDN")

        client_class = RaidenClient.select_client_class(network)
        latest = client_class.get_latest_release()
        if not latest.is_installed:
            self._send_status_update(f"Downloading and installing raiden {latest.release}")
            latest.install()
            self._send_status_update("Installation complete")

        self._send_status_update(
            "Launching Raiden, this might take a couple of minutes, do not close the browser"
        )

        if not latest.is_running:
            latest.launch(configuration_file)

        try:
            latest.wait_for_web_ui_ready()
            self._send_status_update("Raiden is ready!")
        except RaidenClientError as exc:
            self._send_status_update(f"Raiden process failed to start: {exc}")
        else:
            sys.exit()


class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")


class SetupHandler(RequestHandler):
    def get(self):
        self.render(
            "raiden_setup.html",
            configuration_file_names=[
                os.path.basename(f) for f in RaidenConfigurationFile.list_existing_files()
            ],
        )


class LaunchHandler(RequestHandler):
    def get(self, configuration_file_name):
        tracker_websocket_url = "ws://{host}{path}".format(
            host=self.request.host,
            path=self.reverse_url("launch_tracker", configuration_file_name),
        )

        try:
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        except ValueError as exc:
            self.set_status(400)
            self.finish(f"{exc}")

        raiden_client = RaidenClient.select_client_class(configuration_file.network)

        self.render(
            "launch.html",
            tracker_websocket_url=tracker_websocket_url,
            redirect_url=raiden_client.WEB_UI_INDEX_URL,
        )


class AccountFundingHandler(RequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        exchange_rate_websocket_url = "ws://{host}{path}".format(
            host=self.request.host,
            path=self.reverse_url("exchange_rate_tracker", configuration_file_name),
        )
        tracker_websocket_url = "ws://{host}{path}".format(
            host=self.request.host, path=self.reverse_url("swap_tracker")
        )

        self.render(
            "account_funding.html",
            configuration_file=configuration_file,
            funding_amounts=[RDNAmount(amount) for amount in FUNDING_AMOUNTS],
            exchange_rate_websocket_url=exchange_rate_websocket_url,
            tracker_websocket_url=tracker_websocket_url,
            redirect_url=self.reverse_url("launch", configuration_file.file_name),
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

    def post(self):
        json_data = json.loads(self.request.body)
        form_data = {k: [str(v)] for k, v in json_data.items()}
        form = QuickSetupForm(form_data)
        if form.validate():
            network = Network.get_by_name(form.data["network"])
            url_or_infura_id = form.data["endpoint"].strip()

            if Infura.is_valid_project_id(url_or_infura_id):
                ethereum_rpc_provider = Infura.make(network, url_or_infura_id)
            else:
                ethereum_rpc_provider = EthereumRPCProvider(url_or_infura_id)

            account = Account.create()

            conf_file = RaidenConfigurationFile(
                account,
                network,
                ethereum_rpc_provider.url,
                routing_mode="pfs" if form.data["use_rsb"] else "local",
                enable_monitoring=form.data["use_rsb"],
            )
            conf_file.save()
            self.set_status(201)
            self.set_header(
                "Location", self.reverse_url("api-configuration-detail", conf_file.file_name)
            )
        else:
            self.set_status(400)
            self.render_json({"errors": form.errors})


class ConfigurationItemAPIHandler(APIHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )
        eth_balance = configuration_file.account.get_ethereum_balance(w3)
        self.render_json(
            {
                "file_name": configuration_file.file_name,
                "launch_url": self.reverse_url("launch", configuration_file.file_name),
                "account": configuration_file.account.address,
                "network": configuration_file.network.name,
                "balance": {"wei": eth_balance.as_wei, "formatted": eth_balance.formatted},
            }
        )


if __name__ == "__main__":
    app = Application(
        [
            url(r"/", IndexHandler),
            url(r"/setup", SetupHandler, name="setup"),
            url(r"/funding/(.*)", AccountFundingHandler, name="funding"),
            url(r"/launch/(.*)", LaunchHandler, name="launch"),
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
        static_path=os.path.join(get_data_folder_path(), "static"),
        template_path=os.path.join(get_data_folder_path(), "templates"),
    )
    app.listen(PORT)

    if not DEBUG:
        webbrowser.open_new(f"http://localhost:{PORT}")
    tornado.ioloop.IOLoop.current().start()
