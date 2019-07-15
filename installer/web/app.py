import logging
from urllib.parse import urlparse
import webbrowser

from flask import Flask, render_template, request, redirect
from flask.logging import default_handler

from .. import base


app = Flask(__name__)

for logger in (app.logger, base.logger):
    logger.addHandler(default_handler)


def build_configuration_file(req):
    network = base.Network.get_by_name(req.form["network-name"])

    endpoint_url = req.form["rpc-or-infura-project-id"].strip()

    def is_valid_url(url):
        parsed_url = urlparse(url)
        return bool(parsed_url.scheme) and bool(parsed_url.netloc)

    if base.Infura.is_valid_project_id(endpoint_url):
        ethereum_rpc_provider = base.Infura.make(network, endpoint_url)
    elif is_valid_url(endpoint_url):
        ethereum_rpc_provider = base.EthereumRPCProvider(endpoint_url)
    else:
        raise ValueError("Not a valid Project ID / Endpoint URL")

    account = base.Account.create()
    conf_file = base.RaidenConfigurationFile(
        account, network, ethereum_rpc_provider.url
    )
    conf_file.save()
    return conf_file


@app.route("/", methods=["GET"])
def index():
    configuration_files = base.RaidenConfigurationFile.get_available_configurations()
    return render_template("index.html", configuration_files=configuration_files)


@app.route("/launch", methods=["POST"])
@app.route("/launch/<configuration_file_name>", methods=["POST"])
def launch(configuration_file_name=None):
    if configuration_file_name is not None:
        configuration_file = base.RaidenConfigurationFile.get_by_filename(
            configuration_file_name
        )
    else:
        try:
            configuration_file = build_configuration_file(request)
        except ValueError as exc:
            return render_template("index.html", error_message=exc.message)

    latest = base.RaidenClient.get_latest_release()
    if not latest.is_installed:
        latest.install()

    account = configuration_file.account
    network = configuration_file.network

    try:
        if configuration_file.balance == 0:
            app.logger.info(f"Low balance. Adding funds to {account.address}")
            network.fund(account)
    except Exception as exc:
        app.logger.exception(exc)

    app.logger.info(
        f"Current balance for {account.address}: ETH {configuration_file.balance}"
    )

    token = base.Token(
        ethereum_rpc_endpoint=configuration_file.ethereum_client_rpc_endpoint,
        account=configuration_file.account,
    )
    try:
        if token.balance == 0:
            app.logger.info(
                f"Minting and depositing {token.TOKEN_AMOUNT} tokens for {token.owner}"
            )
            token.mint(token.TOKEN_AMOUNT)
            token.deposit(token.TOKEN_AMOUNT)
    except Exception as exc:
        app.logger.exception(exc)

    latest.launch(configuration_file)
    return redirect(base.RaidenClient.WEB_UI_INDEX_URL)


if __name__ == "__main__":
    if not app.debug:
        webbrowser.open_new("http://localhost:5000")
    app.run()
