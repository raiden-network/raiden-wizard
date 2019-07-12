import socket
import webbrowser

from flask import Flask, render_template, request

from ..base import (
    Account,
    Network,
    RaidenClient,
    RaidenConfigurationFile,
    build_infura_url,
    is_valid_infura_project_id,
)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def install_raiden():
    if request.method == "POST":
        passphrase = request.form["keystore-pwd"]
        project_id = request.form["proj-id"]

        if not passphrase == "" and is_valid_infura_project_id(project_id):
            account = Account.create(passphrase)
            network = Network.get_by_name("goerli")
            ethereum_client_rpc_endpoint = build_infura_url(network, project_id)

            raiden_configuration_file = RaidenConfigurationFile(
                account, network, ethereum_client_rpc_endpoint
            )
            raiden_configuration_file.save()

            RaidenClient.get_latest_release().install()
        else:
            return """ERROR"""

    return render_template("install-raiden.html")


if __name__ == "__main__":
    new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_socket.bind(("127.0.0.1", 0))
    port = new_socket.getsockname()[1]

    # Skips port where Raiden will be running
    if port == 5001:
        port += 1

    new_socket.close()

    webbrowser.open_new(f"http://127.0.0.1:{port}/")
    app.run(host="127.0.0.1", port=f"{port}")
