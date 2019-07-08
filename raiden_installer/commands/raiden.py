import os
import requests
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile
from tarfile import TarFile


def latest_raiden_release() -> str:
    try:
        res = requests.get(
            'https://api.github.com/repos/raiden-network/raiden/releases'
        )
    except requests.exceptions.RequestException as err:
        print(
            'Could not retrieve latest release data from the GitHub API,'
            ' please try again later'
        )

    try:
        latest_raiden_release = res.json()[0].get('tag_name')
        return latest_raiden_release
    except json.JSONDecodeError as err:
        print(
            'Could not retrieve latest release data, response object is'
            ' not valid JSON'
        )
    except IndexError as err:
        print(
            'Could not retrieve latest release data, index of list does'
            ' not exist'
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
        f'{raiden_release}/raiden-'
        f'{raiden_release}-{platform}-x86_64.{archive}'
    )
    return raiden_download_url


def download_raiden_archive(raiden_download_url: str, binary_dir: Path) -> Path:
    try:
        res = requests.get(raiden_download_url)
        file_content = res.content
    except requests.exceptions.RequestException as err:
        print(
            'Could not retrieve Raiden archive from GitHub,'
            ' please try again later'
        )

    filename = Path(raiden_download_url).name
    archive = Path(binary_dir).joinpath(filename)

    try:
        with open(archive, 'wb') as f:
            f.write(file_content)

        return archive
    except OSError as err:
        print('Unable to download archive')


def unpack_raiden_binary(archive: Path, binary_dir: Path) -> Path:
    archive_format = Path(archive).suffix

    try:
        if archive_format == '.zip':
            with ZipFile(archive) as f:
                f.extractall(binary_dir)
                archive_content = f.namelist()[0]
        elif archive_format == '.gz':
            with TarFile.open(archive) as f:
                f.extractall(binary_dir)
                archive_content = f.getnames()[0]
        else:
            raise FileNotFoundError
        
        # Delete archive after binary has been extracted
        os.remove(archive)

        binary = Path(binary_dir).joinpath(archive_content)
        return binary
    except FileNotFoundError:
        print('Unable to find any archive')


def initialize_raiden(binary: Path, config_file: Path) -> None:
    # Set permissions to run binary
    os.chmod(binary, 0o770)

    subprocess.Popen([binary, '--config-file', config_file])

# Comment