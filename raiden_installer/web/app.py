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
from ..token_exchange import Exchange, TokenNetwork, RaidenTokenNetwork


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
            "swap": self._run_swap,
        }.get(method)

        return action and action(**data)

    def _run_close(self, **kw):
        sys.exit()

    def _run_launch(self, **kw):
        configuration_file_name = kw.get("configuration_file_name")
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)

        network = configuration_file.network
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
            self._send_task_complete("Raiden is ready!")
            self._send_redirect(latest.WEB_UI_INDEX_URL)
        except (RaidenClientError, RuntimeError) as exc:
            self._send_error_message(f"Raiden process failed to start: {exc}")
            latest.kill()

    def _run_swap(self, **kw):
        DEPOSIT_TIMEOUT = 5

        log.info(str(kw))

        try:
            configuration_file_name = kw.get("configuration_file_name")
            exchange = kw["exchange"]
            token_amount = kw["amount"]
            token_sticker = kw["token"]
        except (ValueError, KeyError, TypeError) as exc:
            self._send_error_message(f"Invalid request: {exc}")
            return

        try:
            configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
            form = TokenExchangeForm(
                {
                    "network": [configuration_file.network.name],
                    "exchange": [exchange],
                    "token_amount": [token_amount],
                    "token_sticker": [token_sticker],
                }
            )

            if form.validate():
                account = configuration_file.account
                w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)
                token_network_class = TokenNetwork.get_by_sticker(form.data["token_sticker"])
                token_network = token_network_class(w3=w3)

                token_amount = token_network.TOKEN_AMOUNT_CLASS(Wei(form.data["token_amount"]))
                exchange = Exchange.get_by_name(form.data["exchange"])(w3=w3)

                costs = exchange.calculate_transaction_costs(token_amount, account)
                needed_funds = costs["total"]
                current_balance = account.get_ethereum_balance(w3)
                required_deposit_amount = EthereumAmount(
                    Wei(needed_funds.as_wei - current_balance.as_wei)
                )

                if needed_funds > current_balance:
                    self._send_status_update(
                        f"Please deposit at least {required_deposit_amount.formatted} to "
                        f"{account.address} in the next {DEPOSIT_TIMEOUT} minutes"
                    )
                balance = account.wait_for_ethereum_funds(
                    w3, required_deposit_amount, timeout=DEPOSIT_TIMEOUT * 60
                )
                self._send_status_update(f"Account balance now is {balance.formatted}")
                self._send_status_update(f"Acquiring {token_amount.formatted} via {exchange.name}")
                self._send_status_update(f"Estimated costs: {needed_funds.formatted}")
                exchange.buy_tokens(account, token_amount)

                token_balance = token_network.balance(account)
                self._send_task_complete(f"Swap complete. {token_balance.formatted} available")

            else:
                for key, error_list in form.errors.items():
                    error_message = f"{key}: {'/'.join(error_list)}"
                    self._send_error_message(error_message)
        except (json.decoder.JSONDecodeError, KeyError) as exc:
            self._send_error_message(str(exc))


class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")


class SetupHandler(RequestHandler):
    def get(self):
        file_names = [os.path.basename(f) for f in RaidenConfigurationFile.list_existing_files()]
        self.render("raiden_setup.html", configuration_file_names=file_names)


class AccountDetailHandler(RequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        self.render("account.html", configuration_file=configuration_file)


class AccountFundingHandler(RequestHandler):
    def get(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        self.render("funding.html", configuration_file=configuration_file)


class SwapHandler(RequestHandler):
    def get(self, exchange_name, configuration_file_name):
        exchange_class = Exchange.get_by_name(exchange_name)
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        w3 = make_web3_provider(
            configuration_file.ethereum_client_rpc_endpoint, configuration_file.account
        )

        exchange = exchange_class(w3=w3)
        current_balance = configuration_file.account.get_ethereum_balance(w3)
        self.render(
            "swap.html",
            exchange=exchange,
            configuration_file=configuration_file,
            balance=current_balance,
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
        rdn_balance = RaidenTokenNetwork(w3=w3).balance(configuration_file.account)
        eth_balance = configuration_file.account.get_ethereum_balance(w3)

        self.render_json(
            {
                "url": self.reverse_url("api-configuration-detail", configuration_file.file_name),
                "file_name": configuration_file.file_name,
                "account_page_url": self.reverse_url("account", configuration_file.file_name),
                "funding_page_url": self.reverse_url("funding", configuration_file.file_name),
                "account": configuration_file.account.address,
                "network": configuration_file.network.name,
                "balance": {
                    "ETH": {"as_wei": eth_balance.as_wei, "formatted": eth_balance.formatted},
                    "RDN": {"as_wei": rdn_balance.as_wei, "formatted": rdn_balance.formatted},
                },
            }
        )


if __name__ == "__main__":
    app = Application(
        [
            url(r"/", IndexHandler),
            url(r"/setup", SetupHandler, name="setup"),
            url(r"/account/(.*)", AccountDetailHandler, name="account"),
            url(r"/funding/(.*)", AccountFundingHandler, name="funding"),
            url(r"/swap/(kyber|uniswap)/(.*)", SwapHandler, name="swap"),
            url(r"/ws", AsyncTaskHandler, name="websocket"),
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
