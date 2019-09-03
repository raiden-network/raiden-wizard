import hashlib
import uuid

import requests

from .typing import ETH_UNIT


class FundingError(Exception):
    pass


class Network:
    MINIMUM_ETHEREUM_BALANCE_REQUIRED = ETH_UNIT("0.01")
    FAUCET_AVAILABLE = False
    KYBER_RDN_EXCHANGE = False
    UNISWAP_RDN_EXCHANGE = False

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
    def all():
        return [Network.get_by_name(n) for n in Network.get_network_names()]

    @staticmethod
    def get_by_chain_id(chain_id):
        return Network.get_by_name(
            [name for name, cid in Network.CHAIN_ID_MAPPING.items() if cid == chain_id].pop()
        )

    @staticmethod
    def get_by_name(name):
        network_class = {
            "mainnet": Mainnet,
            "ropsten": Ropsten,
            "rinkeby": Rinkeby,
            "goerli": Goerli,
            "kovan": Kovan,
        }.get(name, Network)
        return network_class()


class Mainnet(Network):
    KYBER_RDN_EXCHANGE = True
    UNISWAP_RDN_EXCHANGE = True


class Goerli(Network):
    FAUCET_AVAILABLE = True

    def fund(self, account):
        try:
            # client_hash = hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()
            client_hash = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
            response = requests.post(
                "https://faucet.workshop.raiden.network/",
                json={"address": account.address, "client_hash": client_hash},
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}")


class Ropsten(Network):
    KYBER_RDN_EXCHANGE = True

    def fund(self, account):
        try:
            response = requests.get(f"https://faucet.ropsten.be/donate/{account.address}")
            response.raise_for_status()
        except Exception as exc:
            raise FundingError(f"Failed to get funds from faucet: {exc}")


class Rinkeby(Network):
    UNISWAP_RDN_EXCHANGE = True


class Kovan(Network):
    pass
