import unittest

from raiden_contracts.constants import CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import get_contracts_deployment_info
from raiden_installer.utils import get_contract_address


class UtilsTestCase(unittest.TestCase):
    def test_can_get_contract_address(self):
        udc_address = get_contract_address(1, CONTRACT_USER_DEPOSIT)

        deployment_info = get_contracts_deployment_info(1)
        expected_udc_address = deployment_info["contracts"][CONTRACT_USER_DEPOSIT]["address"]
        self.assertEqual(udc_address, expected_udc_address)

    def test_cannot_get_invalid_contract_address(self):
        with self.assertRaises(ValueError):
            get_contract_address(1, "invalid contract name")
