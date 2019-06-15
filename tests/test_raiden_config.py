import builtins
from unittest.mock import patch, mock_open
from raiden_installer.installer_parts import raiden_config


@patch('builtins.open', new_callable=mock_open())
def test_create_plain_txt_pwd_file_path(mock_open_file):
    '''
    Tests that the path to the pwd file is accessible
    from the class variable once a plain txt pwd file
    has been created.
    '''
    plain_txt_pwd = raiden_config.PlainTxtPwd('/dest/dir/path', 'password')
    plain_txt_pwd.create_plain_txt_pwd_file()

    pwd_file = plain_txt_pwd.pwd_file
    assert str(pwd_file) == '/dest/dir/path/pwd.txt'


def test_eth_rpc_endpoint_url():
    '''
    Tests that a correctly formatted URL
    for the ETH RPC endpoint is returned.
    '''
    eth_rpc = raiden_config.eth_rpc_endpoint(
        '  6a9a5919fc3e4d2088b2512b0da8926a  ',
        'goerli'
    )
    assert eth_rpc == (
        'https://goerli.infura.io/v3/6a9a5919fc3e4d2088b2512b0da8926a'
    )