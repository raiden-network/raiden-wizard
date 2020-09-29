import time
from re import search
from urllib.parse import urlparse

import requests
import structlog
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.eth import Eth
from web3.exceptions import BlockNotFound
from web3.gas_strategies.time_based import construct_time_based_gas_price_strategy
from web3.middleware import construct_sign_and_send_raw_middleware, simple_cache_middleware
from web3.types import Wei

from raiden_installer.account import Account
from raiden_installer.constants import ETH_GAS_STATION_API, GAS_PRICE_MARGIN
from raiden_installer.network import Network

log = structlog.get_logger()

EXTRA_DATA_LENGTH = 66  # 32 bytes hex encoded + `0x` prefix
WEB3_BLOCK_NOT_FOUND_RETRY_COUNT = 3


def make_web3_provider(url: str, account: Account) -> Web3:
    w3 = Web3(HTTPProvider(url))
    w3.middleware_onion.add(simple_cache_middleware)
    if is_infura(w3):
        # Infura sometimes erroneously returns `null` for existing (but very recent) blocks.
        # Work around this by retrying those requests.
        # See docstring for details.
        Eth.getBlock = make_patched_web3_get_block(Eth.getBlock)  # type: ignore

    def gas_price_strategy_eth_gas_station_or_with_margin(web3: Web3, transaction_params):
        # FIXME: This is a temporary fix to speed up gas price generation
        # by fetching from eth_gas_station if possible.
        # Once we have a reliable gas price calculation this can be removed
        if int(web3.net.version) == 1:
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
    w3.middleware_onion.inject(make_sane_poa_middleware, layer=0)

    return w3


class EthereumRPCProvider:
    def __init__(self, url):
        self.url = url


class Infura(EthereumRPCProvider):
    URL_PATTERN = "https://{network_name}.infura.io:443/v3/{project_id}"
    ID_REGEX = r"(^|(?<=(infura\.io\/v[\d]\/)))[\da-fA-F]{32}$"

    def __init__(self, url):
        super().__init__(url)
        if not Infura.is_valid_project_id(self.project_id):
            raise ValueError(f"{url} is not a valid URL and/or infura project")

        try:
            self.network
        except KeyError as exc:
            raise ValueError(f"{url} contains an invalid ethereum network") from exc

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


def make_sane_poa_middleware(make_request, web3: Web3):  # pylint: disable=unused-argument
    """ Simpler geth_poa_middleware that doesn't break with ``null`` responses. """

    def middleware(method, params):
        response = make_request(method, params)
        result = response.get("result")
        is_get_block_poa = (
            method.startswith("eth_getBlockBy")
            and result is not None
            and len(result["extraData"]) != EXTRA_DATA_LENGTH
        )
        if is_get_block_poa:
            extra_data = result.pop("extraData")
            response["result"] = {**result, "proofOfAuthorityData": HexBytes(extra_data)}
        return response

    return middleware


def make_patched_web3_get_block(original_func):
    """ Patch Eth.getBlock() to retry in case of ``BlockNotFound``

    Infura sometimes erroneously returns a `null` response for
    ``eth_getBlockByNumber`` and ``eth_getBlockByHash`` for existing blocks.

    This generates a wrapper method that tries to perform the request up to
    ``WEB3_BLOCK_NOT_FOUND_RETRY_COUNT`` times.

    If no result is returned after the final retry the last ``BlockNotFound`` exception is
    re-raised.

    See:
      - https://github.com/raiden-network/raiden/issues/3201
      - https://github.com/INFURA/infura/issues/43
    """

    def patched_web3_get_block(  # type: ignore
        self, block_identifier, full_transactions: bool = False
    ):
        last_ex = None
        for remaining_retries in range(WEB3_BLOCK_NOT_FOUND_RETRY_COUNT, 0, -1):
            try:
                return original_func(self, block_identifier, full_transactions)
            except BlockNotFound as ex:
                log.warning(
                    "Block not found, retrying",
                    remaining_retries=remaining_retries - 1,
                    block_identifier=block_identifier,
                )
                last_ex = ex
                # Short delay
                time.sleep(0.1)
        if last_ex is not None:
            raise last_ex

    return patched_web3_get_block


def is_infura(web3: Web3) -> bool:
    return (
        isinstance(web3.provider, HTTPProvider)
        and web3.provider.endpoint_uri is not None
        and "infura.io" in web3.provider.endpoint_uri
    )
