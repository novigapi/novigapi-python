"""Devig every two-sided Novig market in a league.

    export NOVIGAPI_KEY=nv_...
    python examples/devig_board.py --league NFL --method shin --limit 100

For each open two-way market it takes the taker prices (asks) on both sides,
removes the margin with the chosen method and prints the fair probability and
fair American odds. The spread between the two asks is the "vig" on an
exchange: Novig adds no bookmaker margin, but a taker still crosses the spread.
"""

from __future__ import annotations

import argparse

from _markets import NovigAPI, two_sides
from novigapi.devig import METHODS, devig, hold, prob_to_american


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--league", required=True, help="league code, such as NFL, NBA, NHL, NCAAF")
    parser.add_argument("--method", default="multiplicative", choices=sorted(METHODS))
    parser.add_argument("--limit", type=int, default=100, help="markets per page")
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args()

    api = NovigAPI()
    header = "{:<52} {:<22} {:>6} {:>6} {:>7} {:>8}".format("market", "outcome", "ask", "fair", "fair US", "spread")
    print(header)
    print("-" * len(header))
    shown = 0
    for market in api.iter_rows("markets", league=args.league, status="open", limit=args.limit, max_pages=args.max_pages):
        sides = two_sides(api, market)
        if not sides:
            continue
        asks = [sides[0]["ask"], sides[1]["ask"]]
        if sum(asks) <= 1.0:
            # Crossed or locked book: no margin to remove. arb_scanner.py looks at these.
            continue
        fair = devig(asks, args.method)
        label = (market.get("description") or market["market_id"])[:52]
        for side, p in zip(sides, fair):
            print("{:<52} {:<22} {:>6.3f} {:>6.3f} {:>+7.0f} {:>7.2%}".format(
                label, str(side["name"])[:22], side["ask"], p, prob_to_american(p), hold(asks)))
            label = ""
        shown += 1
    print("\n{} two-sided markets devigged with the {} method.".format(shown, args.method))


if __name__ == "__main__":
    main()
