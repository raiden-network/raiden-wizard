from unittest.mock import patch
from datetime import datetime
from raiden_installer.installer_parts import keystore


@patch('raiden_installer.installer_parts.keystore.datetime')
@patch('raiden_installer.installer_parts.keystore.uuid4')
def test_generate_keyfile_name(mock_uuid4, mock_datetime):
    '''
    Tests that a correctly formatted
    keyfile name is returned.
    '''
    mock_datetime.utcnow.return_value = datetime(1986, 6, 5)
    mock_uuid4.return_value = 'abc-def-012-345-6789'

    keyfile_name = keystore.generate_keyfile_name()
    assert keyfile_name == 'UTC--1986-06-05T00-00-00Z--abc-def-012-345-6789'