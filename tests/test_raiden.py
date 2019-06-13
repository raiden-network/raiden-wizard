from unittest.mock import patch, call
from raiden_installer import raiden


@patch('raiden_installer.raiden.requests')
def test_latest_raiden_release_name_get_request_url(mock_requests):
    '''
    Tests that requests.get is called with the correct URL
    '''
    latest_raiden_release_name = raiden.latest_raiden_release_name()

    # Grab args that requests.get was called with
    args = mock_requests.get.call_args

    assert args == call(
        'https://api.github.com/repos/raiden-network/raiden/releases'
    )


@patch('raiden_installer.raiden.requests')
def test_latest_raiden_release_name_returns_tag_name(mock_requests):
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

    latest_raiden_release_name = raiden.latest_raiden_release_name()

    assert latest_raiden_release_name == 'raiden-v3'


def test_():
    pass