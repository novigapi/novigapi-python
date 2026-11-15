import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from novigapi import taker_fee  # noqa: E402
from novigapi.devig import (  # noqa: E402
    additive,
    american_to_prob,
    devig,
    hold,
    multiplicative,
    power,
    prob_to_american,
    shin,
)


def close(a, b, tol=1e-4):
    return abs(a - b) <= tol


def test_conversions():
    assert close(american_to_prob(-110), 110 / 210)
    assert close(american_to_prob(150), 0.4)
    assert close(prob_to_american(0.4), 150.0)
    assert close(prob_to_american(0.6), -150.0)


def test_even_market_all_methods_agree():
    q = [american_to_prob(-110), american_to_prob(-110)]
    assert close(hold(q), 1 - 1 / (220 / 210))
    for method in ("multiplicative", "additive", "power", "shin"):
        p = devig(q, method)
        assert close(p[0], 0.5) and close(p[1], 0.5)


def test_lopsided_market():
    q = [american_to_prob(-300), american_to_prob(240)]
    m = multiplicative(q)
    a = additive(q)
    pw = power(q)
    s = shin(q)
    assert close(m[0], 0.71831)
    assert close(a[0], 0.72794)
    assert close(pw[0], 0.73308)
    # With two outcomes, Shin and additive give the same answer.
    assert close(s[0], a[0])
    # Power takes the most margin from the longshot, multiplicative the least.
    assert pw[1] < a[1] < m[1]
    for p in (m, a, pw, s):
        assert close(math.fsum(p), 1.0, 1e-9)


def test_taker_fee_matches_novig_docs():
    # docs.novig.com worked examples: 100 contracts at 0.50 -> $1.50, at 0.30 -> $1.26.
    assert close(taker_fee(0.50, 100), 1.50)
    assert close(taker_fee(0.30, 100), 1.26)
    assert close(taker_fee(0.45, 500), 7.425)
