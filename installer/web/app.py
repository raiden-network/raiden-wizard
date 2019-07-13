import webbrowser

from flask import Flask, render_template

from ..base import RaidenConfigurationFile

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def launch_screen():
    configuration_files = RaidenConfigurationFile.get_available_configurations()

    # TODO: This commented out code should be refactored in accordance with the new lauhc screen
    # if request.method == "POST":
    # passphrase = request.form["keystore-pwd"]
    # project_id = request.form["proj-id"]

    # if not passphrase == "" and is_valid_infura_project_id(project_id):
    #     account = Account.create(passphrase)
    #     network = Network.get_by_name("goerli")
    #     ethereum_client_rpc_endpoint = build_infura_url(network, project_id)

    #     raiden_configuration_file = RaidenConfigurationFile(
    #         account, network, ethereum_client_rpc_endpoint
    #     )
    #     raiden_configuration_file.save()

    #     RaidenClient.get_latest_release().install()
    # else:
    #     return """ERROR"""

    return render_template(
        "launch-screen.html", configuration_files=configuration_files
    )


if __name__ == "__main__":
    webbrowser.open_new("http://127.0.0.1:5000/")
    app.run(host="127.0.0.1", port="5000")
