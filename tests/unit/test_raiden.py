import unittest
from datetime import datetime
from pathlib import Path

from raiden_installer.raiden import (
    RaidenNightly,
    RaidenRelease,
    RaidenTestnetRelease,
    VersionData,
    temporary_passphrase_file,
)


class RaidenClientTestCase(unittest.TestCase):
    def test_create_raiden_release(self):
        version_data = VersionData("1", "1", "0")
        raiden_release = RaidenRelease("https://test.download.url", version_data)
        self.assertEqual(raiden_release.version, "Raiden 1.1.0")
        self.assertEqual(raiden_release.binary_name, "raiden-1.1.0")
        self.assertIsNone(raiden_release.version_modifier)
        self.assertIsNone(raiden_release.version_modifier_number)

    def test_create_raiden_testnet_release(self):
        version_data = VersionData("0", "200", "0", "-rc9")
        raiden_release = RaidenTestnetRelease("https://test.download.url", version_data)
        self.assertEqual(raiden_release.version, "Raiden Preview 0.200.0-rc9 (Testnet only)")
        self.assertEqual(raiden_release.binary_name, "raiden-testnet-0.200.0-rc9")
        self.assertEqual(raiden_release.version_modifier, "rc")
        self.assertEqual(raiden_release.version_modifier_number, "9")

    def test_create_raiden_nightly(self):
        version_data = VersionData("0", "200", "0", "rc4.dev9+gea6de43f9")
        release_datetime = datetime(2020, 4, 3, 0, 26, 35)
        raiden_release = RaidenNightly(version_data, release_datetime)
        self.assertEqual(
            raiden_release.version,
            "Raiden Nightly Build 0.200.0rc4.dev9+gea6de43f9-20200403"
        )
        self.assertEqual(
            raiden_release.binary_name,
            "raiden-nightly-0.200.0rc4.dev9+gea6de43f9-20200403"
        )
        self.assertEqual(raiden_release.version_modifier, "rc")
        self.assertEqual(raiden_release.version_modifier_number, "4")

    def test_raiden_testnet_binary_name(self):
        version_data_1 = VersionData("0", "100", "5", "a0")
        raiden_release_1 = RaidenTestnetRelease("https://test.download.url", version_data_1)
        version_data_2 = VersionData("1", "0", "2", "-rc")
        raiden_release_2 = RaidenTestnetRelease("https://test.download.url", version_data_2)

        self.assertEqual(raiden_release_1.binary_name, "raiden-testnet-0.100.5a0")
        self.assertEqual(raiden_release_2.binary_name, "raiden-testnet-1.0.2-rc")

    def test_get_version_data(self):
        release_name = f"raiden-v1.1.1-{RaidenRelease.FILE_NAME_SUFFIX}"
        version_data = RaidenRelease._get_version_data(release_name)
        self.assertEqual(version_data, VersionData("1", "1", "1"))

    def test_get_nightly_release_data(self):
        release_name = (
            "NIGHTLY/raiden-nightly-2020-04-07T00-29-38-v0.200.0rc4.dev11+g2d9d1fcfc-" +
            RaidenNightly.FILE_NAME_SUFFIX
        )
        result = RaidenNightly._get_release_data(release_name)
        self.assertEqual(
            result,
            (
                VersionData("0", "200", "0", "rc4.dev11+g2d9d1fcfc"),
                datetime(2020, 4, 7, 0, 29, 38)
            )
        )

    def test_temporary_passphrase_file(self):
        password = "test_password"
        with temporary_passphrase_file(password) as file_path:
            passphrase_file = Path(file_path)
            temporary_password = passphrase_file.read_text()
            self.assertEqual(temporary_password, password)
        self.assertFalse(passphrase_file.exists())
