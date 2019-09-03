import json
import logging
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from tornado.log import enable_pretty_logging
from tornado.web import Application, RequestHandler, url
from tornado.websocket import WebSocketHandler
from wtforms_tornado import Form

from ..base import Account, RaidenConfigurationFile
from ..network import Network
from ..raiden import RaidenClient, RaidenClientError
from ..ethereum_rpc import Infura, EthereumRPCProvider, make_web3_provider
from ..token_exchange import CustomToken, RaidenToken, Exchange, ExchangeError


DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ
PORT = 8888


log = logging.getLogger("tornado.application")
log.setLevel(logging.DEBUG if DEBUG else logging.INFO)
enable_pretty_logging()


AVAILABLE_NETWORKS = Network.all()


def get_data_folder_path():
    # Find absolute path for non-code resources (static files, templates) When
    # we are running in development, it will just be the same folder as this
    # file, but when bundled by pyinstaller, it will be placed on the folder
    # indicated by sys._MEIPASS
    return getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)


class QuickSetupForm(Form):
    network = wtforms.SelectField(
        choices=[(n.name, n.capitalized_name) for n in AVAILABLE_NETWORKS]
    )
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


class LauncherStatusNotificationHandler(WebSocketHandler):
    def _send_status_update(self, message_text, message_type="info", complete=False):
        self.write_message(
            json.dumps({"type": message_type, "text": message_text, "complete": complete})
        )
        log.info(message_text)

    def open(self, configuration_file_name):
        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)

        account = configuration_file.account
        network = configuration_file.network
        w3 = make_web3_provider(configuration_file.ethereum_client_rpc_endpoint, account)

        raiden_token = RaidenToken(w3=w3, account=account)
        custom_token = CustomToken(w3=w3, account=account)

        ethereum_amount = network.MINIMUM_ETHEREUM_BALANCE_REQUIRED

        has_faucet = network.FAUCET_AVAILABLE
        needed_funds = ethereum_amount - account.get_ethereum_balance(w3)
        needs_funding = any(
            [
                raiden_token.is_available(network) and not raiden_token.is_funded,
                custom_token.is_available(network) and not custom_token.is_funded,
            ]
        )

        try:
            if needs_funding and needed_funds <= 0:
                self._send_status_update(f"Account is funded with enough ETH to swap for tokens")
            elif needs_funding and needed_funds > 0 and has_faucet:
                self._send_status_update(f"Funding account with {network.capitalized_name} ETH")
                network.fund(account)
                self._send_status_update(f"ETH successfully acquired", message_type="success")
            elif needs_funding:
                self._send_status_update(
                    f"Please send at least {needed_funds:0.4f} ETH to 0x{account.address} on "
                    f"{network.capitalized_name}"
                )
                account.wait_for_ethereum_funds(w3, network)
            else:
                self._send_status_update(f"ETH funding not required at the moment")
            self._send_status_update(
                f"Current balance: {account.get_ethereum_balance(w3):0.4f} ETH"
            )
        except Exception as exc:
            self._send_status_update(
                f"Failed to add funds to account: {exc}", message_type="warning"
            )

        if custom_token.is_available(network):
            if not custom_token.is_funded:
                try:
                    self._send_status_update(f"Obtaining tokens")
                    custom_token.mint(CustomToken.TOKEN_AMOUNT)
                    custom_token.deposit(CustomToken.TOKEN_AMOUNT)
                    self._send_status_update(
                        "Raiden successfully funded with tokens", message_type="success"
                    )
                except Exception as exc:
                    self._send_status_update(
                        f"Failed to pre-mint custom tokens.", message_type="error"
                    )
                    self._send_status_update(
                        f"You should still be able to do it on Raiden Web UI: {exc}",
                        message_type="error",
                    )

        if raiden_token.is_available(network):
            if not raiden_token.is_funded:
                try:
                    self._send_status_update(f"Running ETH <-> RDN Swap")
                    exchange = Exchange.select_by_rate(w3, account, ethereum_amount)
                    exchange_rate = exchange.get_current_rate(ethereum_amount)
                    self._send_status_update(
                        f"{exchange.name} has the best rate of {exchange_rate:0.4f} RDN/ETH"
                    )
                    exchange.swap_ethereum_for_rdn(ethereum_amount, exchange_rate)
                except ExchangeError as exc:
                    self._send_status_update(
                        f"Failed to exchange ETH for RDN: {exc}", message_type="error"
                    )
            else:
                self._send_status_update(f"Account has already {raiden_token.balance:0.4f} RDN")

        client_class = RaidenClient.select_client_class(network)
        latest = client_class.get_latest_release()
        if not latest.is_installed:
            self._send_status_update(f"Downloading and installing raiden {latest.release}")
            latest.install()
            self._send_status_update("Installation complete", message_type="success")

        self._send_status_update(
            "Launching Raiden, this might take a couple of minutes, do not close the browser"
        )

        if not latest.is_running:
            latest.launch(configuration_file)

        try:
            latest.wait_for_web_ui_ready()
            self._send_status_update("Raiden is ready!", complete=True)
        except RaidenClientError as exc:
            self._send_status_update(f"Raiden process failed to start: {exc}")
        else:
            sys.exit()


class IndexHandler(RequestHandler):
    def get(self):
        configuration_files = RaidenConfigurationFile.get_available_configurations()
        self.render(
            "index.html",
            configuration_files=configuration_files,
            setup_form=QuickSetupForm(),
            errors=[],
        )


class LaunchHandler(RequestHandler):
    def get(self, configuration_file_name):
        websocket_url = "ws://{host}{path}".format(
            host=self.request.host, path=self.reverse_url("status", configuration_file_name)
        )

        configuration_file = RaidenConfigurationFile.get_by_filename(configuration_file_name)
        raiden_client = RaidenClient.select_client_class(configuration_file.network)

        self.render(
            "launch.html", websocket_url=websocket_url, raiden_url=raiden_client.WEB_UI_INDEX_URL
        )


class QuickSetupHandler(LaunchHandler):
    def post(self):
        form = QuickSetupForm(self.request.arguments)
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
            return self.redirect(self.reverse_url("launch", conf_file.file_name))
        else:
            return self.render(
                "index.html",
                configuration_files=RaidenConfigurationFile.get_available_configurations(),
                setup_form=form,
            )


if __name__ == "__main__":
    app = Application(
        [
            url(r"/", IndexHandler),
            url(r"/launch/(.*)", LaunchHandler, name="launch"),
            url(r"/setup", QuickSetupHandler, name="quick_setup"),
            url(r"/ws/(.*)", LauncherStatusNotificationHandler, name="status"),
        ],
        debug=DEBUG,
        static_path=os.path.join(get_data_folder_path(), "static"),
        template_path=os.path.join(get_data_folder_path(), "templates"),
    )
    app.listen(PORT)

    if not DEBUG:
        webbrowser.open_new(f"http://localhost:{PORT}")
    tornado.ioloop.IOLoop.current().start()
