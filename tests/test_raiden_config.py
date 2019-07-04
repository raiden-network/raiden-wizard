import builtins
from pathlib import Path
from unittest.mock import patch, mock_open
from raiden_installer.installer_parts import raiden_config


@patch('builtins.open', new_callable=mock_open())
def test_create_plain_txt_pwd_file_path(mock_open_file):
    '''
    Tests that the path to the pwd file is accessible
    from the class variable once a plain txt pwd file
    has been created.
    '''
    plain_txt_pwd = raiden_config.PlainTextPassword('/config/dir/path', 'password')
    plain_txt_pwd.create_plain_txt_pwd_file()

    pwd_file = plain_txt_pwd.pwd_file
    assert str(pwd_file) == '/config/dir/path/pwd.txt'


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


@patch('builtins.open', new_callable=mock_open())
@patch('raiden_installer.installer_parts.raiden_config.toml')
def test_generate_raiden_config_file_data(mock_toml, mock_open_file):
    '''
    Tests that expected configuration
    data is written to the TOML file.
    '''
    config_data = {
        "environment-type": "development",
        "keystore-path": "/keystore/dir/path/keystore",
        "address": "0x4a01C085EA70Ae37487641cb78fa973BB6C310a4",
        "password-file": "/config/dir/path/pwd.txt",
        "user-deposit-contract-address": (
            "0x6978D210a7F69527a210C0942ED7520045FE1a29"
        ),
        "network-id": "goerli",
        "accept-disclaimer": True,
        "eth-rpc-endpoint": (
            "https://goerli.infura.io/v3/6a9a5919fc3e4d2088b2512b0da8926a"
        ),
        "routing-mode": "pfs",
        "pathfinding-service-address": (
            "https://pfs-goerli.services-dev.raiden.network"
        ),
        "enable-monitoring": True
    }

    raiden_config.generate_raiden_config_file(
        '/config/dir/path',
        '/keystore/dir/path',
        'https://goerli.infura.io/v3/6a9a5919fc3e4d2088b2512b0da8926a',
        '4a01c085ea70ae37487641cb78fa973bb6c310a4',
        '0x6978D210a7F69527a210C0942ED7520045FE1a29'
    )

    toml_output = mock_toml.dump.call_args[0][0]
    assert toml_output == config_data


@patch('builtins.open', new_callable=mock_open())
def test_generate_raiden_config_file_returns_path(mock_open_file):
    '''
    Tests that path to the generated config file is returned
    '''
    config_file = raiden_config.generate_raiden_config_file(
        '/config/dir/path',
        '/keystore/dir/path',
        'https://goerli.infura.io/v3/6a9a5919fc3e4d2088b2512b0da8926a',
        '4a01c085ea70ae37487641cb78fa973bb6c310a4',
        '0x6978D210a7F69527a210C0942ED7520045FE1a29'
    )
    assert config_file == Path('/config/dir/path/config.toml')