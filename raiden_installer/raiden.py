import requests
import json


def latest_raiden_release() -> str:
    try:
        res = requests.get(
            'https://api.github.com/repos/raiden-network/raiden/releases'
        )
    except requests.exceptions.RequestException as err:
        print(
            'Could not retrieve latest release data from the GitHub API,'
            + ' please try again later'
        )

    try:
        latest_raiden_release = res.json()[0].get('tag_name')
        return latest_raiden_release
    except json.JSONDecodeError as err:
        print(
            'Could not retrieve latest release data, response object is'
            + ' not valid JSON'
        )
    except IndexError as err:
        print(
            'Could not retrieve latest release data, index of list does'
            + ' not exist'
        )
    except KeyError as err:
        print('Could not retrieve "tag_name" from JSON response object')


def raiden_download_url(raiden_release: str, platform: str) -> str:
    '''
    Builds the URL from which to download the
    Raiden archive based on the users system.
    '''
    if platform == 'macOS':
        archive = 'zip'
    elif platform == 'linux':
        archive = 'tar.gz'

    raiden_download_url = (
        'https://github.com/raiden-network/raiden/releases/download/'
        + f'{raiden_release}/raiden-'
        + f'{raiden_release}-{platform}-x86_64.{archive}'
    )
    return raiden_download_url


def download_raiden_archive(raiden_download_url: str, dest_dir: str) -> str:
    pass