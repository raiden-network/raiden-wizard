import sys
import json
import time
import socket
import webbrowser
from pathlib import Path
from web3 import Web3, HTTPProvider
from eth_utils import to_checksum_address
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)
from installer_parts import (
    keystore,
    raiden_config,
    funding,
    raiden
)
from constants import (
    PLATFORM,
    BINARY_DIR,
    CONFIG_DIR,
    KEYSTORE_DIR,
    TOKEN_AMOUNT,
    GAS_PRICE,
    GAS_REQUIRED_FOR_MINT,
    GAS_REQUIRED_FOR_APPROVE,
    GAS_REQUIRED_FOR_DEPOSIT
)


def static_assets_absolute_path(static_assets_relative_path: str) -> Path:
    '''
    Provides PyInstaller with an
    absolute path to static files.
    '''
    installer_server_file = Path(__file__).resolve()
    raiden_installer_dir = installer_server_file.parent
    base_path = getattr(sys, '_MEIPASS', raiden_installer_dir)

    static_assets_absolute_path = Path(base_path).joinpath(
        static_assets_relative_path
    )
    return static_assets_absolute_path


if getattr(sys, 'frozen', False):
    # Installer code running in a bundle
    template_folder = static_assets_absolute_path('templates')
    static_folder = static_assets_absolute_path('static')

    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder
    )
else:
    # Installer code running live
    app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def install_raiden():
    if request.method == 'POST':
        keystore_pwd = request.form['keystore-pwd']
        proj_id = request.form['proj-id']
        network = 'goerli'

        '''
        Installer Step 1

        Create keystore directory and
        retrieve keyfile and address.
        '''
        keyfile = keystore.make_keystore(
            KEYSTORE_DIR,
            keystore.generate_keyfile_name(),
            keystore_pwd
        )

        with open(keyfile, 'r') as f:
            keyfile_content = json.load(f)

        address = keyfile_content['address']

        '''
        Installer Step 2

        Build the ETH RPC endpoint URL
        '''
        eth_rpc = raiden_config.eth_rpc_endpoint(proj_id, network)

        '''
        Installer Step 3

        Grab ETH and confirm that the
        account address has a balance.
        '''
        eth_acquisition = funding.goerli_funding(address)
        w3 = Web3(HTTPProvider(eth_rpc))

        while w3.eth.getBalance(to_checksum_address(address)) <= 0:
            time.sleep(1)
            print('Not enough ETH on account address')

        '''
        Installer Step 4

        Acquire tokens for PFS and Monitoring services
        and retrieve the user deposit contract address.
        '''
        private_key = keystore.get_private_key(keyfile_content, keystore_pwd)
        pfs_monitoring_funding = funding.PfsAndMonitoringFunding(
            w3,
            to_checksum_address(address),
            private_key
        )
        user_deposit_address = pfs_monitoring_funding.user_deposit_address

        mint_tokens = pfs_monitoring_funding.mint_tokens(
            TOKEN_AMOUNT,
            GAS_REQUIRED_FOR_MINT,
            GAS_PRICE
        )
        print('Status')
        print(mint_tokens)

        approve_deposit = pfs_monitoring_funding.approve_deposit(
            TOKEN_AMOUNT,
            GAS_REQUIRED_FOR_APPROVE,
            GAS_PRICE
        )
        print('Status')
        print(approve_deposit)

        make_deposit = pfs_monitoring_funding.make_deposit(
            TOKEN_AMOUNT,
            GAS_REQUIRED_FOR_DEPOSIT,
            GAS_PRICE
        )
        print('Status')
        print(make_deposit)

        '''
        Installer Step 5

        Create a plain txt pwd file
        and generate a TOML config.
        '''
        plain_txt_pwd = raiden_config.PlainTextPassword(CONFIG_DIR, keystore_pwd)
        plain_txt_pwd.create_plain_txt_pwd_file()

        global config_file
        config_file = raiden_config.generate_raiden_config_file(
            CONFIG_DIR,
            KEYSTORE_DIR,
            eth_rpc,
            address,
            user_deposit_address
        )

        '''
        Installer Step 6

        Download Raiden archive
        and unpack the binary.
        '''
        latest_raiden_release = raiden.latest_raiden_release()
        raiden_download_url = raiden.raiden_download_url(
            latest_raiden_release,
            PLATFORM
        )
        archive = raiden.download_raiden_archive(
            raiden_download_url,
            BINARY_DIR
        )

        global binary
        binary = raiden.unpack_raiden_binary(
            archive,
            BINARY_DIR
        )

        return redirect(url_for('run_raiden'))
    return render_template('install-raiden.html')


@app.route('/run-raiden', methods=['GET', 'POST'])
def run_raiden():
    if request.method == 'POST':
        '''
        Installer Step 7

        Initialize Raiden and open the
        WebUI in a new browser window.
        '''
        raiden.initialize_raiden(
            binary,
            config_file
        )

    return render_template('run-raiden.html')


if __name__ == '__main__':
    new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_socket.bind(('127.0.0.1', 0))
    port = new_socket.getsockname()[1]

    # Skips port where Raiden will be running
    if port == 5001:
        port += 1

    new_socket.close()

    webbrowser.open_new(f'http://127.0.0.1:{port}/')
    app.run(host='127.0.0.1', port=f'{port}')