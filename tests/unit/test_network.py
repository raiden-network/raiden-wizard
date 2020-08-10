import unittest
from pathlib import Path

from raiden_installer.account import Account
from raiden_installer.network import Network

CHAIN_ID_MAPPING = {"mainnet": 1, "ropsten": 3, "rinkeby": 4, "goerli": 5, "kovan": 42}


class NetworkTestCase(unittest.TestCase):
    def test_get_network_names(self):
        self.assertEqual(Network.get_network_names(), list(CHAIN_ID_MAPPING.keys()))

    def test_get_network_by_name(self):
        for name, cid in CHAIN_ID_MAPPING.items():
            network = Network.get_by_name(name)
            self.assertEqual(network.name, name)
            self.assertEqual(network.chain_id, cid)

    def test_get_network_by_chain_id(self):
        for name, cid in CHAIN_ID_MAPPING.items():
            network = Network.get_by_chain_id(cid)
            self.assertEqual(network.name, name)
            self.assertEqual(network.chain_id, cid)
