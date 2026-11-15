"""Shared helpers for the examples: pull the two sides of a Novig market.

Prices are probabilities from 0 to 1. Novig's book holds bids only, so the
price a taker pays for an outcome (its ask) is 1 minus the best bid on the
other outcome. When the API row already carries ask_price, that is used.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from novigapi import NovigAPI  # noqa: E402

Side = Dict[str, Any]


def _num(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 < v < 1.0 else None


def two_sides(api: NovigAPI, market: Dict[str, Any]) -> Optional[Tuple[Side, Side]]:
    """Return the two outcomes of a two-way market with bid and ask filled in, or None."""
    outcomes: List[Dict[str, Any]] = market.get("outcomes") or []
    if len(outcomes) != 2:
        full = api.market(market["market_id"]).get("data") or {}
        outcomes = full.get("outcomes") or []
    if len(outcomes) != 2:
        return None
    a, b = outcomes
    bid_a, bid_b = _num(a.get("bid_price")), _num(b.get("bid_price"))
    ask_a = _num(a.get("ask_price")) or (1.0 - bid_b if bid_b is not None else None)
    ask_b = _num(b.get("ask_price")) or (1.0 - bid_a if bid_a is not None else None)
    if ask_a is None or ask_b is None:
        return None
    return (
        {"name": a.get("name") or "side A", "outcome_id": a.get("outcome_id"), "bid": bid_a, "ask": ask_a},
        {"name": b.get("name") or "side B", "outcome_id": b.get("outcome_id"), "bid": bid_b, "ask": ask_b},
    )
