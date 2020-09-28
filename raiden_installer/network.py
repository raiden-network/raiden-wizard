from __future__ import annotations

import hashlib
import uuid

import requests
from eth_utils import to_checksum_address


class FundingError(Exception):
    pass


class Network:
    FAUCET_AVAILABLE = False

    CHAIN_ID_MAPPING = {"mainnet": 1, "ropsten": 3, "rinkeby": 4, "goerli": 5, "kovan": 42}

    def __init__(self):
        self.chain_id = self.CHAIN_ID_MAPPING[self.name.lower()]

    @property
    def name(self):
        return self.__class__.__name__.lower()

    @property
    def capitalized_name(self):
        return self.name.capitalize()

    def fund(self, account):
        raise NotImplementedError(
            "Each network should implement its own method to fund an account"
        )

    @staticmethod
    def get_network_names():
        return list(Network.CHAIN_ID_MAPPING.keys())

    @staticmethod
    def get_by_chain_id(chain_id: int) -> Network:
        return Network.get_by_name(
            [name for name, cid in Network.CHAIN_ID_MAPPING.items() if cid == chain_id].pop()
        )

    @staticmethod
    def get_by_name(name: str) -> Network:
        network_class = NETWORK_CLASSES.get(name, Network)
        return network_class()


class Mainnet(Network):
    pass


class Goerli(Network):
    FAUCET_AVAILABLE = True

    def fund(self, account):
        try:
            # client_hash = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()
            client_hash = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
            response = requests.post(
                "https://faucet.workshop.raiden.network/",
                json={"address": to_checksum_address(account.address), "client_hash": client_hash},
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}") from exc


class Ropsten(Network):
    FAUCET_AVAILABLE = True

    def fund(self, account):
        try:
            response = requests.get(
                f"https://faucet.ropsten.be/donate/{to_checksum_address(account.address)}"
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}") from exc


class Rinkeby(Network):
    pass


class Kovan(Network):
    pass


NETWORK_CLASSES = {
    "mainnet": Mainnet,
    "ropsten": Ropsten,
    "rinkeby": Rinkeby,
    "goerli": Goerli,
    "kovan": Kovan,
}
