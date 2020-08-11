import unittest
from pathlib import Path

from raiden_installer.raiden import temporary_passphrase_file


class RaidenClientTestCase(unittest.TestCase):
    def test_temporary_passphrase_file(self):
        password = "test_password"
        with temporary_passphrase_file(password) as file_path:
            passphrase_file = Path(file_path)
            temporary_password = passphrase_file.read_text()
            self.assertEqual(temporary_password, password)
        self.assertFalse(passphrase_file.exists())
