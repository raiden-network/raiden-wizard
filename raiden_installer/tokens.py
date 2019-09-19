from typing import NewType, TypeVar, Generic
from decimal import Decimal, getcontext

Eth_T = TypeVar("Eth_T", int, Decimal, float, str, "Wei")
Token_T = TypeVar("Token_T")
TokenSticker = NewType("TokenSticker", str)


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
        return self.sticker == other.sticker and self.amount == other.amount

    def __lt__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")
        return self.amount < other.sticker

    def __gt__(self, other):
        if not self.sticker == other.sticker:
            raise ValueError(f"Can not compare {self.sticker} with {other.sticker}")
        return self.amount > other.sticker


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
