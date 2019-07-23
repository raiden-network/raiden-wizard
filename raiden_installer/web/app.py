import json
import logging
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import tornado.ioloop
import wtforms
from raiden_installer import RAIDEN_CLIENT_DEFAULT_CLASS, base
from tornado.log import enable_pretty_logging
from tornado.web import Application, RequestHandler, url
from tornado.websocket import WebSocketHandler
from wtforms_tornado import Form

DEBUG = "RAIDEN_INSTALLER_DEBUG" in os.environ
PORT = 8888


log = logging.getLogger("tornado.application")
log.setLevel(logging.DEBUG if DEBUG else logging.INFO)
enable_pretty_logging()


AVAILABLE_NETWORKS = [n for n in base.Network.all() if n.FAUCET_AVAILABLE]


def get_data_folder_path():
    # Find absolute path for non-code resources (static files, templates) When
    # we are running in development, it will just be the same folder as this
    # file, but when bundled by pyinstaller, it will be placed on the folder
    # indicated by sys._MEIPASS
    return getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)


class QuickSetupForm(Form):
    network = wtforms.HiddenField(default=base.Network.get_by_name("goerli").name)
    use_rsb = wtforms.BooleanField("Use Raiden Service Bundle", default=True)
    endpoint = wtforms.StringField("Infura Project ID/RPC Endpoint")

    def validate_network(self, field):
        network_name = field.data
        if network_name not in [n.name for n in AVAILABLE_NETWORKS]:
            raise wtforms.ValidationError(
                f"Can not run quick setup raiden with {network_name}"
            )

    def validate_endpoint(self, field):
        data = field.data.strip()
        parsed_url = urlparse(data)
        is_valid_url = bool(parsed_url.scheme) and bool(parsed_url.netloc)
        is_valid_project_id = base.Infura.is_valid_project_id(data)

        if not (is_valid_project_id or is_valid_url):
            raise wtforms.ValidationError("Not a valid URL nor Infura Project ID")


class LauncherStatusNotificationHandler(WebSocketHandler):
    def _send_status_update(self, message_text, message_type="info", complete=False):
        self.write_message(
            json.dumps(
                {"type": message_type, "text": message_text, "complete": complete}
            )
        )
        log.info(message_text)

    def open(self, configuration_file_name):
        configuration_file = base.RaidenConfigurationFile.get_by_filename(
            configuration_file_name
        )

        account = configuration_file.account
        network = configuration_file.network

        try:
            if configuration_file.balance == 0:
                self._send_status_update(f"No ETH funds in account.")
                self._send_status_update(
                    f"Obtaining ETH from {network.capitalized_name} faucet"
                )
                network.fund(account)
                self._send_status_update(
                    f"ETH acquired for {account.address}", message_type="success"
                )
            self._send_status_update(
                f"Current balance: {configuration_file.balance} WEI"
            )
        except Exception as exc:
            self._send_status_update(
                f"Failed to add funds to account: {exc}", message_type="warning"
            )

        token = base.Token(
            ethereum_rpc_endpoint=configuration_file.ethereum_client_rpc_endpoint,
            account=configuration_file.account,
        )
        try:
            if token.balance == 0:
                self._send_status_update(
                    f"Minting and depositing {token.TOKEN_AMOUNT} tokens for {token.owner}"
                )
                token.mint(token.TOKEN_AMOUNT)
                token.deposit(token.TOKEN_AMOUNT)
                self._send_status_update(
                    "Raiden account funded and able to operate", message_type="success"
                )
        except Exception as exc:
            self._send_status_update(
                f"Failed to execute token contracts: {exc}", message_type="error"
            )

        latest = RAIDEN_CLIENT_DEFAULT_CLASS.get_latest_release()
        if not latest.is_installed:
            self._send_status_update(
                f"Downloading and installing raiden {latest.release}"
            )
            latest.install()
            self._send_status_update("Installation complete", message_type="success")

        self._send_status_update("Launching raiden")

        if not latest.is_running:
            latest.launch(configuration_file)

        try:
            latest.wait_for_web_ui_ready()
            self._send_status_update("Raiden is ready!", complete=True)
        except base.RaidenClientError as exc:
            self._send_status_update(f"Raiden process failed to start: {exc}")
        else:
            sys.exit()


class IndexHandler(RequestHandler):
    def get(self):
        configuration_files = (
            base.RaidenConfigurationFile.get_available_configurations()
        )
        self.render(
            "index.html",
            configuration_files=configuration_files,
            setup_form=QuickSetupForm(),
            errors=[],
        )


class LaunchHandler(RequestHandler):
    def get(self, configuration_file_name):
        websocket_url = "ws://{host}{path}".format(
            host=self.request.host,
            path=self.reverse_url("status", configuration_file_name),
        )

        self.render(
            "launch.html",
            websocket_url=websocket_url,
            raiden_url=RAIDEN_CLIENT_DEFAULT_CLASS.WEB_UI_INDEX_URL,
        )


class QuickSetupHandler(LaunchHandler):
    def post(self):
        form = QuickSetupForm(self.request.arguments)
        if form.validate():
            network = base.Network.get_by_name(form.data["network"])
            url_or_infura_id = form.data["endpoint"].strip()

            if base.Infura.is_valid_project_id(url_or_infura_id):
                ethereum_rpc_provider = base.Infura.make(network, url_or_infura_id)
            else:
                ethereum_rpc_provider = base.EthereumRPCProvider(url_or_infura_id)

            account = base.Account.create()

            conf_file = base.RaidenConfigurationFile(
                account,
                network,
                ethereum_rpc_provider.url,
                routing_mode="pfs" if form.data["use_rsb"] else "local",
                enable_monitoring=form.data["use_rsb"],
            )
            conf_file.save()
            return self.redirect(self.reverse_url("launch", conf_file.file_name))


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
