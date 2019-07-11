import socket
import webbrowser

from flask import Flask, render_template, request

from ..base import (
    Account,
    RaidenConfigurationFile,
    Network,
    build_infura_url,
    RaidenClient,
)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def install_raiden():
    if request.method == "POST":
        passphrase = request.form["keystore-pwd"]
        project_id = request.form["proj-id"]

        # Creates a keystore in my case on mac it is located in /users/taleldayekh/Library/Ethereum/keystore
        account = Account.create(passphrase)

        # Create a network object so we can grab the relevant network name. The network "goerli in this case" should be passed via radio button
        network = Network("goerli")

        # Build the ETH RPC Endpoint for Inura
        ethereum_client_rpc_endpoint = build_infura_url(network.name, project_id)

        # Here we create our configuration file in my case on mac it is located in /users/taleldayeky/.local/share/raiden
        raiden_config_file = RaidenConfigurationFile(
            account, network, ethereum_client_rpc_endpoint
        )
        raiden_config_file.save()

        # Download and install latest Raiden release
        RaidenClient.get_latest_release().install()

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
