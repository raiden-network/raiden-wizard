from typing import NewType, TypeVar, Generic
from decimal import Decimal, getcontext

Eth_T = TypeVar("Eth_T", int, Decimal, float, str, "Wei")
Token_T = TypeVar("Token_T")
TokenSticker = NewType("TokenSticker", str)

RDN_ADDRESSES = {
    "mainnet": "0x255aa6df07540cb5d3d297f0d0d4d84cb52bc8e6",
    "ropsten": "0x5422Ef695ED0B1213e2B953CFA877029637D9D26",
    "rinkeby": "0x51892e7e4085df269de688b273209f3969f547e0",
    "kovan": "0x3a03155696708f517c53ffc4f696dfbfa7743795",
    "goerli": "0x06b05eb77f6d7c4e7449105d36c7e04fa9cff3ca",
}

DAI_ADDRESSES = {
    "mainnet": "0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359",
    "ropsten": "0xaD6D458402F60fD3Bd25163575031ACDce07538D",
    "rinkeby": "0x2448eE2641d78CC42D7AD76498917359D961A783",
    "kovan": "0xc4375b7de8af5a38a93548eb8453a498222c4ff2",
}


class Wei(int):
    pass


class TokenAmount(Generic[Eth_T]):
    STICKER = None
    WEI_STICKER = None
    DECIMALS = 18

    def __init__(self, value: Eth_T):
        context = getcontext()
        context.prec = self.DECIMALS
        self.value = Decimal(str(value), context=context)
        if type(value) is Wei:
            self.value /= 10 ** self.DECIMALS

    @property
    def sticker(self) -> TokenSticker:
        return TokenSticker(self.STICKER)

    @property
    def formatted(self):
        wei_amount = Decimal(self.as_wei)

        if wei_amount == 0:
            sticker = self.sticker
            value = wei_amount
        elif wei_amount >= 10 ** 15:
            sticker = self.sticker
            value = wei_amount / 10 ** self.DECIMALS
        elif 10 ** 12 <= wei_amount < 10 ** 15:
            sticker = "T" + self.WEI_STICKER
            value = wei_amount / 10 ** 12
        elif 10 ** 9 <= wei_amount < 10 ** 12:
            sticker = "G" + self.WEI_STICKER
            value = wei_amount / 10 ** 9
        elif 10 ** 6 <= wei_amount < 10 ** 9:
            sticker = "M" + self.WEI_STICKER
            value = wei_amount / 10 ** 6
        else:
            sticker = self.WEI_STICKER
            value = wei_amount

        integral = int(value)
        frac = value % 1
        frac_string = f"{frac:.3g}"[1:] if frac else ""

        return f"{integral}{frac_string} {sticker}"

    @property
    def as_wei(self) -> Wei:
        return Wei(self.value * (10 ** 18))

    def __repr__(self):
        return f"{self.value} {self.sticker}"

    def __eq__(self, other):
        return self.sticker == other.sticker and self.as_wei == other.as_wei

    def __lt__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")
        return self.as_wei < other.as_wei

    def __le__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")

        return self.sticker <= other.sticker

    def __gt__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")
        return self.as_wei > other.as_wei

    def __ge__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")

        return self.sticker >= other.sticker

    @staticmethod
    def make(sticker: TokenSticker, amount: Wei):
        currency_class = {
            "ETH": EthereumAmount,
            "RDN": RDNAmount,
            "DAI": DAIAmount,
            "LDN": GoerliRaidenAmount,
        }[sticker]

        return currency_class(amount)


class EthereumAmount(TokenAmount):
    STICKER = "ETH"
    WEI_STICKER = "WEI"


class RDNAmount(TokenAmount):
    STICKER = "RDN"
    WEI_STICKER = "REI"


class DAIAmount(TokenAmount):
    STICKER = "DAI"
    WEI_STICKER = "DEI"


class GoerliRaidenAmount(TokenAmount):
    STICKER = "LDN"
    WEI_STICKER = "REI"
