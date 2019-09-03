from enum import Enum

CHAIN_ID_TO_NETWORK_MAPPING = {1: "mainnet", 4: "rinkeby", 42: "kovan"}


class UniswapFactoryAddress(Enum):
    mainnet = "0xc0a47dFe034B400B47bDaD5FecDa2621de6c4d95"
    rinkeby = "0xf5D915570BC477f9B8D6C0E980aA81757A3AaC36"
    kovan = "0xD3E51Ef092B2845f10401a0159B2B96e8B6c3D30"


def get_factory_address(chain_id: int) -> str:
    network_name = CHAIN_ID_TO_NETWORK_MAPPING[chain_id]

    return UniswapFactoryAddress[network_name].value
