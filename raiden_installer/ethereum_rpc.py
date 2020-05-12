from re import search
from urllib.parse import urlparse

import requests
import structlog
from web3 import HTTPProvider, Web3
from web3.gas_strategies.time_based import construct_time_based_gas_price_strategy
from web3.middleware import (
    construct_sign_and_send_raw_middleware,
    geth_poa_middleware,
    simple_cache_middleware,
)
from web3.types import Wei

from raiden_installer.account import Account
from raiden_installer.constants import ETH_GAS_STATION_API, GAS_PRICE_MARGIN
from raiden_installer.network import Network

log = structlog.get_logger()


def make_web3_provider(url: str, account: Account) -> Web3:
    w3 = Web3(HTTPProvider(url))
    w3.middleware_onion.add(simple_cache_middleware)

    def gas_price_strategy_eth_gas_station_or_with_margin(web3: Web3, transaction_params):
        # FIXME: This is a temporary fix to speed up gas price generation
        # by fetching from eth_gas_station if possible.
        # Once we have a reliable gas price calculation this can be removed
        try:
            response = requests.get(ETH_GAS_STATION_API)
            if response and response.status_code == 200:
                data = response.json()
                log.debug(f"fetched gas price: {Wei(int(data['fast'] * 10e7 * 1.1))} Wei")
                return Wei(int(data["fast"] * 10e7 * 1.1))
        except (TimeoutError, ConnectionError, KeyError):
            log.debug("Could not fetch from ethgasstation. Falling back to web3 gas estimation.")

        gas_price_strategy = construct_time_based_gas_price_strategy(
            max_wait_seconds=15, sample_size=25
        )
        gas_price = Wei(int(gas_price_strategy(web3, transaction_params) * GAS_PRICE_MARGIN))
        return gas_price

    w3.eth.setGasPriceStrategy(gas_price_strategy_eth_gas_station_or_with_margin)

    if account.passphrase is not None:
        w3.middleware_onion.add(construct_sign_and_send_raw_middleware(account.private_key))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

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
    ID_REGEX = "(^|(?<=(infura\.io\/v[\d]\/)))[\da-fA-F]{32}$"

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
        project_id = project_id[-32:]
        return cls(cls.URL_PATTERN.format(network_name=network.name, project_id=project_id))

    @staticmethod
    def is_valid_project_id_or_endpoint(id_string: str) -> bool:
        return bool(search(Infura.ID_REGEX, id_string))

    @staticmethod
    def is_valid_project_id(id_string: str) -> bool:
        return len(id_string) == 32 and Infura.is_valid_project_id_or_endpoint(id_string)
