"""Scan Novig two-way markets for a combined price below 1 after the taker fee.

    export NOVIGAPI_KEY=nv_...
    python examples/arb_scanner.py --league NBA
    python examples/arb_scanner.py --league NBA --other other_prices.csv

Buying $1 of payout on each side of a two-way market pays exactly $1 at
settlement. If the two prices plus the taker fee on each come to less than $1,
the pair locks in a profit.

Taker fee per $1 of payout (docs.novig.com, checked 12 Nov 2026; a v3
contract pays 1 cent, so this is the fee on 100 contracts):

    fee_per_dollar = 0.06 x p x (1 - p)

Game markets charge it only while the event is live, so pregame fills are
fee-free; futures markets charge it always. This script charges it on every leg by default, which is the
conservative case. Pass --pregame-free to skip it on markets that are not live.

Inside one Novig book a combined ask below 1 means a crossed book, which is
rare and short-lived. The more useful scan pairs a Novig price on one side with
another venue's price on the other: pass --other with a CSV of
market_id,side,price (side is A or B, price a probability) that you collected
yourself. Other venues' fees are not modelled; add them to their prices.
"""

from __future__ import annotations

import argparse
import csv
from typing import Dict, Tuple

from _markets import NovigAPI, two_sides
from novigapi import taker_fee


def load_other(path: str) -> Dict[Tuple[str, str], float]:
    prices: Dict[Tuple[str, str], float] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            p = float(row["price"])
            if 0.0 < p < 1.0:
                prices[(row["market_id"], row["side"].strip().upper())] = p
    return prices


def leg_cost(price: float, charge_fee: bool, coefficient: float) -> float:
    return price + (taker_fee(price, 1.0, coefficient) if charge_fee else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--league", required=True)
    parser.add_argument("--other", help="CSV of market_id,side,price from another venue")
    parser.add_argument("--coefficient", type=float, default=0.06, help="Novig taker fee coefficient")
    parser.add_argument("--pregame-free", action="store_true", help="no fee on game markets that are not live")
    parser.add_argument("--min-edge", type=float, default=0.0, help="report only edges above this, in dollars per pair")
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    api = NovigAPI()
    other = load_other(args.other) if args.other else {}
    found = 0
    scanned = 0
    for market in api.iter_rows("markets", league=args.league, status="open", limit=200, max_pages=args.max_pages):
        sides = two_sides(api, market)
        if not sides:
            continue
        scanned += 1
        coef = float(market.get("fee_coefficient") or args.coefficient)
        live = str(market.get("event_status") or market.get("status") or "").upper() in ("OPEN_INGAME", "LIVE")
        charge = not (args.pregame_free and not live)
        a, b = sides
        mid = market["market_id"]
        candidates = [("Novig A + Novig B", leg_cost(a["ask"], charge, coef) + leg_cost(b["ask"], charge, coef))]
        if (mid, "B") in other:
            candidates.append(("Novig A + other B", leg_cost(a["ask"], charge, coef) + other[(mid, "B")]))
        if (mid, "A") in other:
            candidates.append(("other A + Novig B", other[(mid, "A")] + leg_cost(b["ask"], charge, coef)))
        for route, total in candidates:
            edge = 1.0 - total
            if edge > args.min_edge:
                found += 1
                print("{}  {}  cost {:.4f}  edge {:.4f} per $1 pair ({:.2%})  [{} / {}]".format(
                    mid, route, total, edge, edge / total, a["name"], b["name"]))
    print("\nScanned {} two-way markets; {} combinations below $1 after fees.".format(scanned, found))


if __name__ == "__main__":
    main()
