import json
import time
import socket
import webbrowser
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)
from web3 import Web3, HTTPProvider
from eth_utils import to_checksum_address
from installer_parts import (
    keystore,
    raiden_config,
    funding,
    raiden
)
from constants import (
    PLATFORM,
    DEST_DIR,
    TOKEN_AMOUNT,
    GAS_PRICE,
    GAS_MINT,
    GAS_APPROVE,
    GAS_DEPOSIT
)


app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def user_input():
    if request.method == 'POST':
        keystore_pwd = request.form['keystore-pwd']
        network = 'goerli'
        proj_id = request.form['proj-id']

        '''
        Installation Step 1

        Create keystore directory and
        retrieve keyfile and address.
        '''
        keyfile = keystore.make_keystore(
            DEST_DIR,
            keystore.generate_keyfile_name(),
            keystore_pwd
        )

        with open(keyfile, 'r') as f:
            keyfile_content = json.load(f)

        address = keyfile_content['address']

        '''
        Installation Step 2

        Build the ETH RPC endpoint URL
        '''
        eth_rpc = raiden_config.eth_rpc_endpoint(proj_id, network)

        '''
        Installation Step 3

        Acquire ETH and use Web3 to confirm that
        the account address has a balance.
        '''
        eth_funding = funding.goerli_funding(address)
        w3 = Web3(HTTPProvider(eth_rpc))

        while w3.eth.getBalance(to_checksum_address(address)) <= 0:
            time.sleep(1)
            print('Not enough ETH on account address')

        '''
        Installation Step 4

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
            GAS_MINT,
            GAS_PRICE
        )
        print(mint_tokens)

        approve_deposit = pfs_monitoring_funding.approve_deposit(
            TOKEN_AMOUNT,
            GAS_APPROVE,
            GAS_PRICE
        )
        print(approve_deposit)

        make_deposit = pfs_monitoring_funding.make_deposit(
            TOKEN_AMOUNT,
            GAS_DEPOSIT,
            GAS_PRICE
        )
        print(make_deposit)

        '''
        Installation Step 5

        Create a plain txt pwd file
        and generate a TOML config file.
        '''
        plain_txt_pwd = raiden_config.PlainTxtPwd(DEST_DIR, keystore_pwd)
        plain_txt_pwd.create_plain_txt_pwd_file()

        config_file = raiden_config.generate_raiden_config_file(
            DEST_DIR,
            eth_rpc,
            address,
            user_deposit_address
        )

        '''
        Installation Step 6

        Download Raiden archive and
        unpack the Raiden binary.
        '''
        latest_raiden_release = raiden.latest_raiden_release()
        raiden_download_url = raiden.raiden_download_url(
            latest_raiden_release,
            PLATFORM,
        )

        archive = raiden.download_raiden_archive(
            raiden_download_url,
            DEST_DIR
        )
        raiden_binary = raiden.unpack_raiden_binary(
            archive,
            DEST_DIR
        )

    return render_template('user-input.html')


if __name__ == '__main__':
    new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_socket.bind(('127.0.0.1', 0))
    port = new_socket.getsockname()[1]

    # Jumps over port where Raiden will be running
    if port == 5001:
        port += 1

    new_socket.close()

    webbrowser.open_new(f'http://127.0.0.1:{port}/')
    app.run(host='127.0.0.1', port=f'{port}')