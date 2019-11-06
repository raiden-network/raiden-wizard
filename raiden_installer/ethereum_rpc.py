from urllib.parse import urlparse

from web3 import HTTPProvider, Web3
from web3.gas_strategies.time_based import fast_gas_price_strategy
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

from raiden_installer.account import Account
from raiden_installer.network import Network


def make_web3_provider(url: str, account: Account) -> Web3:
    w3 = Web3(HTTPProvider(url))
    w3.eth.setGasPriceStrategy(fast_gas_price_strategy)
    w3.middleware_stack.add(construct_sign_and_send_raw_middleware(account.private_key))
    w3.middleware_stack.inject(geth_poa_middleware, layer=0)

    return w3


class EthereumRPCProvider:
    def __init__(self, url):
        self.url = url

    @staticmethod
    def make_from_url(url):
        try:
            return Infura(url)
        except ValueError:
            return EthereumRPCProvider(url)


class Infura(EthereumRPCProvider):
    URL_PATTERN = "https://{network_name}.infura.io:443/v3/{project_id}"

    def __init__(self, url):
        super().__init__(url)
        if not Infura.is_valid_project_id(self.project_id):
            raise ValueError(f"{url} is not a valid URL and/or infura project")

        if self.network.name not in Network.get_network_names():
            raise ValueError(f"{self.network.name} is no valid ethereum network")

    @property
    def network(self):
        network_name = urlparse(self.url).netloc.split(".")[0]
        return Network.get_by_name(network_name.lower())

    @property
    def project_id(self):
        return self.url.split("/")[-1]

    @classmethod
    def make(cls, network: Network, project_id: str):
        return cls(cls.URL_PATTERN.format(network_name=network.name, project_id=project_id))

    @staticmethod
    def is_valid_project_id(id_string: str) -> bool:
        try:
            # It should an hex string
            int(id_string, 16)
            return len(id_string) == 32
        except ValueError:
            return False
