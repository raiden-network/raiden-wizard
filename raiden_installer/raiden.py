import datetime
import functools
import os
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from contextlib import closing, contextmanager
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from xml.etree import ElementTree

import psutil
import requests
from requests.exceptions import ConnectionError

from raiden_installer import default_settings, log, network_settings


@contextmanager
def temporary_passphrase_file(passphrase):
    fd, passphrase_file_path = tempfile.mkstemp()
    try:
        passfile = open(fd, 'w')
        passfile.write(passphrase)
        passfile.flush()
        yield passphrase_file_path
    finally:
        for _ in range(5):
            passfile.seek(0)
            passfile.write(os.urandom(1024).hex())
            passfile.flush()
        os.close(fd)
        os.unlink(passphrase_file_path)


def extract_version_modifier(release_name):
    if not release_name:
        return None

    pattern = r".*(?P<release>(a|alpha|b|beta|rc))-?(?P<number>\d+)"
    match = re.match(pattern, release_name)

    if not match:
        return None

    release = {
        "a": "alpha",
        "alpha": "alpha",
        "b": "beta",
        "beta": "beta",
        "rc": "rc",
        "dev": "dev",
    }.get(match.groupdict()["release"], "dev")

    return (release, match.groupdict()["number"])


def order_version_modifier(version_modifier):
    types = ["dev", "alpha", "beta", "rc"]
    try:
        return types.index(version_modifier)
    except (ValueError, IndexError):
        return -1


class RaidenClientError(Exception):
    pass


class RaidenClient:
    BINARY_FOLDER_PATH = Path.home().joinpath(".local", "bin")
    BINARY_NAME_FORMAT = "raiden-{release}"
    WEB_UI_INDEX_URL = "http://127.0.0.1:5001"
    RAIDEN_API_STATUS_ENDPOINT = "/api/v1/status"

    RELEASE_INDEX_URL = "https://api.github.com/repos/raiden-network/raiden/releases"
    DOWNLOAD_INDEX_URL = "https://github.com/raiden-network/raiden/releases/download"
    FILE_NAME_SUFFIX = "macOS-x86_64.zip" if sys.platform == "darwin" else "linux-x86_64.tar.gz"

    def __init__(self, **kw):
        for attr, value in kw.items():
            setattr(self, attr, value)

        self._process_id = self.get_process_id()

    def __eq__(self, other):
        return all(
            [
                self.major == other.major,
                self.minor == other.minor,
                self.revision == other.revision,
                self.version_modifier == other.version_modifier,
                self.version_modifier_number == other.version_modifier_number,
            ]
        )

    def __lt__(self, other):
        if self.major != other.major:
            return self.major < other.major

        if self.minor != other.minor:
            return self.minor < other.minor

        if self.revision != other.revision:
            return self.revision < other.revision

        if self.version_modifier != other.version_modifier:
            return order_version_modifier(self.version_modifier) < order_version_modifier(
                other.version_modifier_number
            )

        if self.version_modifier_number and other.version_modifier_number:
            return self.version_modifier_number < other.version_modifier_number

        return False

    def __gt__(self, other):
        if self.major != other.major:
            return self.major > other.major

        if self.minor != other.minor:
            return self.minor > other.minor

        if self.revision != other.revision:
            return self.revision > other.revision

        if self.version_modifier != other.version_modifier:
            return order_version_modifier(self.version_modifier) > order_version_modifier(
                other.version_modifier
            )

        if self.version_modifier_number and other.version_modifier_number:
            return self.version_modifier_number > other.version_modifier_number

        return False

    def __cmp__(self, other):
        if self.__gt__(other):
            return 1
        elif self.__lt__(other):
            return -1
        else:
            return 0

    @property
    def release(self):
        return ".".join(
            str(it) for it in (self.major, self.minor, self.revision, self.release_modifier) if it
        )

    @property
    def release_date(self):
        return datetime.date(year=int(self.year), month=int(self.month), day=int(self.day))

    @property
    def release_modifier(self):
        return (
            self.version_modifier
            and self.version_modifier_number
            and f"{self.version_modifier}{self.version_modifier_number}"
        )

    @property
    def version_modifier(self):
        version_modifier = extract_version_modifier(self.extra)
        return version_modifier and version_modifier[0]

    @property
    def version_modifier_number(self):
        version_modifier = extract_version_modifier(self.extra)
        return version_modifier and version_modifier[1]

    @property
    def version(self):
        return f"{self.major}.{self.minor}.{self.revision}"

    def install(self, force=False):

        if self.install_path.exists() and not force:
            raise RuntimeError(f"{self.install_path} already exists")

        self.BINARY_FOLDER_PATH.mkdir(parents=True, exist_ok=True)

        download = requests.get(self.download_url)
        download.raise_for_status()

        action = self._extract_gzip if self.download_url.endswith("gz") else self._extract_zip

        action(BytesIO(download.content), self.install_path)
        os.chmod(self.install_path, 0o770)

    def uninstall(self):
        if self.install_path.exists():
            self.install_path.unlink()

    def launch(self, configuration_file, passphrase_file):
        proc = subprocess.Popen(
            [
                str(self.install_path),
                "--config-file",
                str(configuration_file.path),
                "--password-file",
                str(passphrase_file),
            ]
        )
        self._process_id = proc.pid

    def kill(self):
        process = self._process_id and psutil.Process(self._process_id)
        if process is not None:
            log.info(f"Killing process {self._process_id}")
            process.kill()
            process.wait()
            self._process_id = self.get_process_id()
            assert self._process_id is None

    def check_status_api(self, status_callback: Callable = None):
        """
        Params:
            status_callback:  A function, that will receive the /status API responses before the
                              status is `ready`.
        """
        log.info("Checking /status endpoint")
        try:
            response = requests.get(
                RaidenClient.WEB_UI_INDEX_URL + RaidenClient.RAIDEN_API_STATUS_ENDPOINT
            )
            if response and response.status_code == 200:
                result = response.json()
                if result.get("status") == "ready":
                    return True
                else:
                    if status_callback is not None:
                        status_callback(result)
        except ConnectionError:
            pass
        return False

    def wait_for_web_ui_ready(self, status_callback: Callable = None):
        """
        Params:
            status_callback:  A function, that will receive the /status API responses before the
                              status is `ready`.
        """
        if not self.is_running:
            raise RuntimeError("Raiden is not running")

        uri = urlparse(self.WEB_UI_INDEX_URL)

        while True:
            self._process_id = self.get_process_id()
            if not self.is_running or self.is_zombie:
                raise RaidenClientError("client process terminated while waiting for web ui")

            log.info("Waiting for raiden to start...")

            while not self.check_status_api(status_callback=status_callback):
                time.sleep(1)

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                try:
                    connected = sock.connect_ex((uri.hostname, uri.port)) == 0
                    if connected:
                        return
                except socket.gaierror:
                    pass
                time.sleep(1)

    def get_process_id(self):
        def is_running_raiden(process):
            try:
                is_raiden = self.binary_name.lower() == process.name().lower()
                is_dead = process.status() is [psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE]

                return is_raiden and not is_dead
            except psutil.ZombieProcess:
                return False

        processes = [p for p in psutil.process_iter() if is_running_raiden(p)]

        try:
            return max(p.pid for p in processes)
        except ValueError:
            return None

    @property
    def binary_name(self):
        return self.BINARY_NAME_FORMAT.format(release=self.release)

    @property
    def is_installed(self):
        return self.install_path.exists()

    @property
    def is_running(self):
        return self.get_process_id() is not None

    @property
    def is_zombie(self):
        if not self._process_id:
            return False

        return psutil.Process(self._process_id).status() == psutil.STATUS_ZOMBIE

    @property
    def install_path(self):
        return Path(self.BINARY_FOLDER_PATH).joinpath(self.binary_name)

    @property
    def download_url(self):
        return self.browser_download_url

    def _extract_zip(self, compressed_data, destination_path):
        with zipfile.ZipFile(compressed_data) as zipped:
            with destination_path.open("wb") as binary_file:
                binary_file.write(zipped.read(zipped.filelist[0]))

    def _extract_gzip(self, compressed_data, destination_path):
        with tarfile.open(mode="r:*", fileobj=compressed_data) as tar:
            with destination_path.open("wb") as binary_file:
                compressed_data = tar.extractfile(tar.getmembers()[0])
                if compressed_data:
                    binary_file.write(compressed_data.read())

    @classmethod
    def get_file_pattern(cls):
        return fr"{cls.FILE_NAME_PATTERN}-{cls.FILE_NAME_SUFFIX}"

    @classmethod
    def get_latest_release(cls):
        return max(cls.get_available_releases())

    @classmethod
    @functools.lru_cache()
    def get_available_releases(cls):
        response = requests.get(cls.RELEASE_INDEX_URL)
        response.raise_for_status()

        return sorted(cls._make_releases(response), reverse=True)

    @classmethod
    def get_installed_releases(cls):
        return [release for release in cls.get_available_releases() if release.is_installed]

    @classmethod
    def _make_release(cls, release_data):
        def get_date(timestamp):
            return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").date()

        for asset_data in release_data.get("assets", []):
            version_data = cls.get_version_data(asset_data["name"])
            release_date = get_date(release_data["published_at"])
            if version_data:
                return cls(
                    year=release_date.year,
                    month=release_date.month,
                    day=release_date.day,
                    browser_download_url=asset_data.get("browser_download_url"),
                    **version_data,
                )

    @classmethod
    def _make_releases(cls, index_response):
        def get_date(timestamp):
            return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").date()

        releases = [cls._make_release(release_data) for release_data in index_response.json()]
        return [release for release in releases if release]

    @classmethod
    def get_version_data(cls, release_name):
        regex = re.match(cls.get_file_pattern(), release_name)
        groups = regex and regex.groupdict()
        return groups and dict(
            major=groups["major"],
            minor=groups["minor"],
            revision=groups["revision"],
            extra=groups.get("extra"),
        )

    @classmethod
    def make_by_tag(cls, release_tag):
        tag_url = f"{cls.RELEASE_INDEX_URL}/tags/{release_tag}"
        response = requests.get(tag_url)
        response.raise_for_status()
        return cls._make_release(response.json())

    @staticmethod
    def get_client(network_name=None):
        settings = network_settings[network_name] if network_name else default_settings
        raiden_class = {
            "testing": RaidenTestnetRelease,
            "mainnet": RaidenRelease,
            "nightly": RaidenNightly,
            "demo_env": RaidenDemoEnv,
        }[settings.client_release_channel]
        return raiden_class.make_by_tag(settings.client_release_version)

    @staticmethod
    def get_all_releases():
        release_channels = [RaidenRelease, RaidenTestnetRelease, RaidenNightly]
        all_releases = {}
        for channel in release_channels:
            for raiden in channel.get_available_releases():
                all_releases[raiden.release] = raiden
        return all_releases


class RaidenRelease(RaidenClient):
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)"

    @property
    def version(self):
        return f"Raiden {self.major}.{self.minor}.{self.revision}"


class RaidenTestnetRelease(RaidenClient):
    BINARY_NAME_FORMAT = "raiden-testnet-{release}"
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)(?P<extra>.*)"

    @property
    def version(self):
        return (
            f"Raiden Preview {self.major}.{self.minor}.{self.revision}{self.extra} (Testnet only)"
        )


class RaidenNightly(RaidenClient):
    BINARY_NAME_FORMAT = "raiden-nightly-{release}"
    RELEASE_INDEX_URL = "https://raiden-nightlies.ams3.digitaloceanspaces.com"
    FILE_NAME_PATTERN = (
        r"raiden-nightly-(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)"
        r"T(?P<hour>\d+)-(?P<minute>\d+)-(?P<second>\d+)-"
        r"v(?P<major>\d+)[.](?P<minor>\d+)[.](?P<revision>\w+)[.](?P<extra>.+)"
    )

    @property
    def version(self):
        return f"Raiden Nightly Build {self.release}"

    @property
    def release(self):
        formatted_date = self.release_date.strftime("%Y%m%d")
        return f"{self.major}.{self.minor}.{self.revision}-{formatted_date}"

    @property
    def download_url(self):
        return (
            f"{self.RELEASE_INDEX_URL}/NIGHTLY/"
            f"raiden-nightly-"
            f"{self.year:04}-{self.month:02}-{self.day:02}"
            f"T{self.hour}-{self.minute}-{self.second}-"
            f"v{self.major}.{self.minor}.{self.revision}.{self.extra}-"
            f"{self.FILE_NAME_SUFFIX}"
        )

    def __eq__(self, other):
        return self.release_date == other.release_date

    def __lt__(self, other):
        return self.release_date < other.release_date

    def __gt__(self, other):
        return self.release_date > other.release_date

    def __cmp__(self, other):
        if self.release_date > other.release_date:
            return 1
        elif self.release_date < other.release_date:
            return -1
        else:
            return 0

    @classmethod
    def make_by_tag(cls, release_tag):
        log.info("Getting list of all nightly releases")
        return {r.release: r for r in cls.get_available_releases()}.get(release_tag)

    @classmethod
    def _make_release(cls, **kw):
        return cls(**kw)

    @classmethod
    def _make_releases(cls, index_response):
        xmlns = "http://s3.amazonaws.com/doc/2006-03-01/"

        def get_children_by_tag(node, tag):
            return node.findall(f"{{{xmlns}}}{tag}", namespaces={"xmlns": xmlns})

        tree = ElementTree.fromstring(index_response.content)

        content_nodes = get_children_by_tag(tree, "Contents")
        all_keys = [get_children_by_tag(node, "Key")[0].text for node in content_nodes]

        releases = []

        for file_key in all_keys:
            result = re.search(cls.get_file_pattern(), file_key)
            if result:
                params = result.groupdict()
                params["year"] = int(params["year"])
                params["month"] = int(params["month"])
                params["day"] = int(params["day"])
                releases.append(cls._make_release(**params))

        return releases


class RaidenDemoEnv(RaidenTestnetRelease):
    @property
    def routing_mode(self):
        return settings.routing_mode  # noqa

    @property
    def matrix_server(self):
        return settings.matrix_server  # noqa

    @property
    def pathfinding_service_address(self):
        return settings.pathfinding_service_address  # noqa
