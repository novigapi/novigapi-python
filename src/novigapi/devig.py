"""Devig (remove the vig from) a set of mutually exclusive prices.

Every function takes implied probabilities that sum to more than 1 (a book with
a margin) and returns fair probabilities that sum to 1. All functions are pure:
no I/O, no global state, standard library only.

Novig quotes prices as probabilities shown as percentages (54% = 0.54). A
sportsbook quotes American or decimal odds; convert those first with
``american_to_prob`` or ``decimal_to_prob``.

Methods:

- ``multiplicative``: divide each probability by the total. The default most
  calculators use.
- ``additive``: subtract an equal share of the margin from each outcome.
- ``power``: find k so that the sum of q_i ** k is 1. Takes more margin from
  longshots than from favourites.
- ``shin``: Shin's (1993) model, which assumes a share z of the money is
  informed. Also shifts margin toward longshots.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence

__all__ = [
    "american_to_prob",
    "decimal_to_prob",
    "prob_to_american",
    "prob_to_decimal",
    "overround",
    "hold",
    "multiplicative",
    "additive",
    "power",
    "shin",
    "devig",
    "METHODS",
]


def american_to_prob(odds: float) -> float:
    """Implied probability of American odds, margin included.

    -110 -> 0.5238..., +150 -> 0.4.
    """
    if odds == 0 or -100 < odds < 100:
        raise ValueError("American odds must be <= -100 or >= +100")
    if odds < 0:
        return -odds / (-odds + 100.0)
    return 100.0 / (odds + 100.0)


def decimal_to_prob(odds: float) -> float:
    """Implied probability of decimal odds. 2.50 -> 0.4."""
    if odds <= 1.0:
        raise ValueError("decimal odds must be greater than 1")
    return 1.0 / odds


def prob_to_american(p: float) -> float:
    """American odds for a probability. 0.4 -> +150, 0.6 -> -150, 0.5 -> +100."""
    _check_prob(p)
    if p > 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def prob_to_decimal(p: float) -> float:
    """Decimal odds for a probability. 0.4 -> 2.5."""
    _check_prob(p)
    return 1.0 / p


def overround(probs: Sequence[float]) -> float:
    """Sum of implied probabilities minus 1. -110/-110 -> 0.047619..."""
    return math.fsum(probs) - 1.0


def hold(probs: Sequence[float]) -> float:
    """Theoretical hold: the share of total stake the book keeps on a balanced book.

    hold = 1 - 1 / sum(probs). -110/-110 -> 0.04545...
    """
    return 1.0 - 1.0 / math.fsum(probs)


def multiplicative(probs: Sequence[float]) -> List[float]:
    """Normalise: p_i = q_i / sum(q).

    Keeps the ratio between outcomes. Also called the proportional or basic method.
    """
    qs = _validate(probs)
    total = math.fsum(qs)
    return [q / total for q in qs]


def additive(probs: Sequence[float]) -> List[float]:
    """Subtract an equal share of the margin: p_i = q_i - (sum(q) - 1) / n.

    On a lopsided market this can push a longshot to zero or below; when that
    happens the outcome is floored at 0 and the rest are renormalised, and the
    result should be treated with suspicion.
    """
    qs = _validate(probs)
    margin = (math.fsum(qs) - 1.0) / len(qs)
    out = [q - margin for q in qs]
    if min(out) <= 0.0:
        out = [max(p, 0.0) for p in out]
        total = math.fsum(out)
        out = [p / total for p in out]
    return out


def power(probs: Sequence[float], tol: float = 1e-12, max_iter: int = 200) -> List[float]:
    """Solve for k with sum(q_i ** k) = 1, then p_i = q_i ** k.

    With a positive margin k > 1, which shrinks small probabilities faster than
    large ones, so longshots carry more of the margin.
    """
    qs = _validate(probs)
    f: Callable[[float], float] = lambda k: math.fsum(q ** k for q in qs) - 1.0
    lo, hi = 1e-6, 1.0
    # sum(q^k) falls as k grows; widen the bracket until it straddles zero.
    while f(hi) > 0.0:
        hi *= 2.0
        if hi > 1e6:
            raise ValueError("power method did not converge")
    k = _bisect(f, lo, hi, tol, max_iter, decreasing=True)
    out = [q ** k for q in qs]
    total = math.fsum(out)
    return [p / total for p in out]


def shin(probs: Sequence[float], tol: float = 1e-12, max_iter: int = 200) -> List[float]:
    """Shin's method.

    For a share z of insider money, the fair probability of outcome i is

        p_i(z) = (sqrt(z^2 + 4 (1 - z) q_i^2 / S) - z) / (2 (1 - z))

    where q_i are the implied probabilities and S is their sum. z is chosen so
    the p_i sum to 1. On a book with no margin z = 0 and p_i = q_i.
    """
    qs = _validate(probs)
    total = math.fsum(qs)
    if total <= 1.0:
        return [q / total for q in qs]

    def fair(z: float) -> List[float]:
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * q * q / total) - z) / (2.0 * (1.0 - z)) for q in qs]

    f = lambda z: math.fsum(fair(z)) - 1.0
    z = _bisect(f, 0.0, 0.999, tol, max_iter, decreasing=True)
    out = fair(z)
    s = math.fsum(out)
    return [p / s for p in out]


METHODS: Dict[str, Callable[[Sequence[float]], List[float]]] = {
    "multiplicative": multiplicative,
    "additive": additive,
    "power": power,
    "shin": shin,
}


def devig(probs: Sequence[float], method: str = "multiplicative") -> List[float]:
    """Devig with the named method: multiplicative, additive, power or shin."""
    try:
        fn = METHODS[method]
    except KeyError:
        raise ValueError("method must be one of: " + ", ".join(METHODS)) from None
    return fn(probs)


def _check_prob(p: float) -> None:
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be between 0 and 1 (exclusive)")


def _validate(probs: Sequence[float]) -> List[float]:
    qs = [float(q) for q in probs]
    if len(qs) < 2:
        raise ValueError("need at least two outcomes")
    for q in qs:
        _check_prob(q)
    return qs


def _bisect(f: Callable[[float], float], lo: float, hi: float, tol: float, max_iter: int, decreasing: bool) -> float:
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        v = f(mid)
        if abs(v) < tol:
            return mid
        if (v > 0.0) == decreasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0
