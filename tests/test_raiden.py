from unittest.mock import patch, call
from raiden_installer.installer_parts import raiden


@patch('raiden_installer.installer_parts.raiden.requests')
def test_latest_raiden_release_get_request_url(mock_requests):
    '''
    Tests that requests.get is called with the correct URL
    '''
    latest_raiden_release = raiden.latest_raiden_release()

    # Grab args that requests.get was called with
    args = mock_requests.get.call_args
    assert args == call(
        'https://api.github.com/repos/raiden-network/raiden/releases'
    )


@patch('raiden_installer.installer_parts.raiden.requests')
def test_latest_raiden_release_returns_tag_name(mock_requests):
    '''
    Tests whether the latest Raiden release data
    is returned from the JSON response object.
    '''
    mock_requests.get().json.return_value = (
        [
            {
                "tag_name": "raiden-v3"
            },
            {
                "tag_name": "raiden-v2"
            },
            {
                "tag_name": "raiden-v1"
            }
        ]
    )

    latest_raiden_release = raiden.latest_raiden_release()
    assert latest_raiden_release == 'raiden-v3'


def test_raiden_download_url_mac_release():
    '''
    Tests that the correct download URL is generated for macOS users
    '''
    platform = 'macOS'

    raiden_download_url = raiden.raiden_download_url('latest-release', platform)
    assert raiden_download_url == (
        'https://github.com/raiden-network/raiden/releases/download/'
        'latest-release/raiden-latest-release-macOS-x86_64.zip'
    )


def test_raiden_download_url_linux_release():
    '''
    Tests that the correct download URL is generated for linux users
    '''
    platform = 'linux'

    raiden_download_url = raiden.raiden_download_url('latest-release', platform)
    assert raiden_download_url == (
        'https://github.com/raiden-network/raiden/releases/download/'
        'latest-release/raiden-latest-release-linux-x86_64.tar.gz'
    )