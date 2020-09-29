import unittest

from eth_utils import to_canonical_address

from raiden_contracts.constants import CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import get_contracts_deployment_info
from raiden_contracts.utils.type_aliases import ChainID
from raiden_installer.utils import get_contract_address


class UtilsTestCase(unittest.TestCase):
    def test_can_get_contract_address(self):
        udc_address = get_contract_address(1, CONTRACT_USER_DEPOSIT)

        deployment_info = get_contracts_deployment_info(ChainID(1))
        assert deployment_info
        expected_udc_address = to_canonical_address(
            deployment_info["contracts"][CONTRACT_USER_DEPOSIT]["address"]
        )
        self.assertEqual(udc_address, expected_udc_address)

    def test_cannot_get_invalid_contract_address(self):
        with self.assertRaises(ValueError):
            get_contract_address(1, "invalid contract name")
