import unittest

from raiden_installer.ethereum_rpc import Infura
from raiden_installer.network import Network


class EthereumRpcProviderTestCase(unittest.TestCase):
    def test_infura_is_valid_project_id_or_endpoint(self):
        valid = [
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc0658db9b2",
            "https://mainnet.infura.io/v3/a7a347de4c103495a4a88dc0658db9b2",
            "36b457de4c103495ada08dc0658db9c3",
            "ropsten.infura.io/v3/8dc0658db9c34c103495a4a8b145e83a",
            "ropsten.infura.io/v4/8dc0658db9c34c103495a4a8b145e83a",
        ]
        invalid = [
            "not-infura.net/a7a347de4c103495a4a88dc0658db9b2",
            "7a347de4c103495a4a88dc0658db9b2",
            "a7a347de4c103495a4a88dc0658db9b2444",
            "a7a347de4c103495a4a88gc044658db9b2",
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc065gdb9b2",
            "goerli.infura.io/v3/a7a347de4c103495a4a88dc044658db9b2",
            "goerli.infura.io/v3/a7a34c103495a4a88dc044658db9b2",
        ]
        for project_id in valid:
            self.assertTrue(Infura.is_valid_project_id_or_endpoint(project_id))
        for project_id in invalid:
            self.assertFalse(Infura.is_valid_project_id_or_endpoint(project_id))

    def test_make_infura_provider(self):
        project_id = "36b457de4c103495ada08dc0658db9c3"
        network = Network.get_by_name("mainnet")
        infura = Infura.make(network, project_id)
        self.assertEqual(infura.url, f"https://{network.name}.infura.io:443/v3/{project_id}")
        self.assertEqual(infura.project_id, project_id)
        self.assertEqual(infura.network.name, network.name)

    def test_cannot_create_infura_provider_with_invalid_project_id(self):
        with self.assertRaises(ValueError):
            Infura("https://mainnet.infura.io:443/v3/7a347de4c103495a4a88dc0658db9b2")

    def test_cannot_create_infura_provider_with_invalid_network(self):
        with self.assertRaises(ValueError):
            Infura("https://invalidnetwork.infura.io:443/v3/36b457de4c103495ada08dc0658db9c3")
