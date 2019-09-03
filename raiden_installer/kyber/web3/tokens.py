from .constants import NETWORK_ADDRESS_MODULES_BY_CHAIN_ID


def get_token_network_address(chain_id: int, token_sticker: str):
    network_module = NETWORK_ADDRESS_MODULES_BY_CHAIN_ID.get(chain_id)

    return network_module.TokenAddress[token_sticker].value
