"""novigapi: Python client for novigapi.com, a read-only Novig market data API.

Independent. Not affiliated with, endorsed by or sponsored by Novig.
"""

__version__ = "0.1.0"

from .client import DEFAULT_BASE_URL, NovigAPI, NovigAPIError, RateLimitError  # noqa: E402
from .devig import (  # noqa: E402
    METHODS,
    additive,
    american_to_prob,
    decimal_to_prob,
    devig,
    hold,
    multiplicative,
    overround,
    power,
    prob_to_american,
    prob_to_decimal,
    shin,
)


def taker_fee(price: float, contracts: float = 1.0, coefficient: float = 0.06) -> float:
    """Novig taker fee in dollars: coefficient x p x (1 - p) per $1 of payout.

    ``contracts`` counts dollars of payout. Novig's v3 API quotes contracts that
    pay 1 cent each, so divide a raw v3 quantity by 100 before passing it here.
    Per docs.novig.com (checked 12 Nov 2026) the coefficient is 0.06 on straight
    contracts. Game markets charge it only while the event is live (pregame
    fills are fee-free); futures markets charge it in every phase. The maker
    pays nothing and earns a credit of 0.25 of the taker fee on game markets
    (0.5 on futures) since 22 Oct 2026. Read the market's fee object when you
    have it.
    """
    if not 0.0 < price < 1.0:
        raise ValueError("price must be between 0 and 1")
    return coefficient * price * (1.0 - price) * contracts


__all__ = [
    "__version__",
    "NovigAPI",
    "NovigAPIError",
    "RateLimitError",
    "DEFAULT_BASE_URL",
    "taker_fee",
    "METHODS",
    "devig",
    "multiplicative",
    "additive",
    "power",
    "shin",
    "american_to_prob",
    "decimal_to_prob",
    "prob_to_american",
    "prob_to_decimal",
    "overround",
    "hold",
]
