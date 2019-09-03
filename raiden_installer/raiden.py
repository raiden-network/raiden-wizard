import os
import sys
import re
import functools
import logging
import datetime
import socket
import subprocess
import time
import tarfile
import zipfile
from contextlib import closing
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests
from xml.etree import ElementTree

from .network import Network

logger = logging.getLogger(__name__)


def extract_version_modifier(release_name):
    pattern = r".*(?P<release>(a|alpha|b|beta))-?(?P<number>\d+)"
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

    def launch(self, configuration_file):
        proc = subprocess.Popen(
            [str(self.install_path), "--config-file", str(configuration_file.path)]
        )
        self._process_id = proc.pid

    def wait_for_web_ui_ready(self):
        if not self.is_running:
            raise RuntimeError("Raiden is not running")

        uri = urlparse(self.WEB_UI_INDEX_URL)

        while True:
            self._process_id = self.get_process_id()
            if not self.is_running:
                raise RaidenClientError("client process terminated while waiting for web ui")

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                logger.info("Waiting for raiden to start...")
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
                binary_file.write(tar.extractfile(tar.getmembers()[0]).read())

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
    def _make_releases(cls, index_response):
        def get_date(timestamp):
            return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").date()

        releases = []
        for release_data in index_response.json():
            for asset_data in release_data.get("assets", []):
                version_data = cls.get_version_data(asset_data["name"])
                release_date = get_date(release_data["published_at"])
                if version_data:
                    releases.append(
                        cls(
                            year=release_date.year,
                            month=release_date.month,
                            day=release_date.day,
                            browser_download_url=asset_data.get("browser_download_url"),
                            **version_data,
                        )
                    )
        return releases

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

    @staticmethod
    def select_client_class(network: Network):
        return RaidenRelease if network.name == "mainnet" else RaidenTestnetRelease


class RaidenRelease(RaidenClient):
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)"

    @property
    def version(self):
        return f"Raiden {self.major}.{self.minor}.{self.revision}"


class RaidenTestnetRelease(RaidenClient):
    BINARY_NAME_FORMAT = "raiden-testnet-{release}"
    FILE_NAME_PATTERN = r"raiden-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)(?P<extra>.+)"

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
        r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<revision>\d+)\.(?P<extra>.+)"
    )

    @property
    def version(self):
        return f"Raiden Nightly Build {self.release}"

    @property
    def release(self):
        formatted_date = self.release_date.strftime("%Y%M%d")
        return f"{self.major}.{self.minor}.{self.revision}-{formatted_date}"

    @property
    def download_url(self):
        return (
            f"{self.RELEASE_INDEX_URL}/"
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
    def _make_releases(cls, index_response):
        xmlns = "http://s3.amazonaws.com/doc/2006-03-01/"

        def get_children_by_tag(node, tag):
            return node.findall(f"{{{xmlns}}}{tag}", namespaces={"xmlns": xmlns})

        tree = ElementTree.fromstring(index_response.content)

        content_nodes = get_children_by_tag(tree, "Contents")
        all_keys = [get_children_by_tag(node, "Key")[0].text for node in content_nodes]

        nightlies = {
            k: v.groupdict()
            for k, v in {key: re.match(cls.get_file_pattern(), key) for key in all_keys}.items()
            if v
        }

        for key, value in nightlies.items():
            nightlies[key]["year"] = int(nightlies[key]["year"])
            nightlies[key]["month"] = int(nightlies[key]["month"])
            nightlies[key]["day"] = int(nightlies[key]["day"])

        return [cls(**nightly) for nightly in nightlies.values()]
