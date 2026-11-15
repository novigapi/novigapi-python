"""Closing-line value backtest on Novig's free daily CSVs. No API key needed.

    python examples/clv_backtest.py --start 2026-08-04 --end 2026-11-11
    python examples/clv_backtest.py --start 2026-10-01 --end 2026-11-11 --bets my_bets.csv
    python examples/clv_backtest.py --start 2026-10-01 --end 2026-11-11 --results results.csv --out per_market.csv

Source: Novig publishes one markets.csv per day at

    https://data.novig.com/reporting/trade-data/<YYYY-MM-DD>/markets.csv

with the columns date, marketId, reportTicker, openInterest, dailyVolume,
open, high, low, close, status. Prices are percentages of the one outcome the
file quotes for each market. Each file is read as a stream, row by row, and
nothing is written to disk unless you pass --out.

What it measures:

- Entry: by default, the first open price the market ever printed (the
  "opening line"). With --bets, your own entry price per market.
- Close: the last close price the market printed on or before --end.
- CLV, in percentage points, for buying the quoted outcome: close - entry.
  Positive means the market moved toward you after you entered.

Closing-line efficiency needs outcomes. The daily CSVs carry no settlement
result, so pass --results with market_id,won (won = 1 if the quoted outcome
won, else 0) to score the opening and closing prices with the Brier score and
log loss. Lower is better; a closing line that is more efficient than the
opening line scores lower.

Efficiency without results (--martingale): if the market is efficient, a
day's price change should not predict the next day's. For every market with
three or more daily closes, the script pairs consecutive close-to-close changes
and reports their correlation and the mean next-day change after a move of each
size. Positive follow-through means slow markets; negative means overreaction.

Caveat: the close column is the last print of the day, and Novig trades
in-game. For a market that traded live, that print can sit close to the final
result, so a large open-to-close move is often the game happening, not the
pregame market correcting itself. The CSVs carry no event start time, so this
script cannot cut at kickoff; treat its "close" as the last traded price.

Combination (parlay) markets are skipped unless you pass --include-combos.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Iterator, List, Optional

BASE = "https://data.novig.com/reporting/trade-data/{day}/markets.csv"


def days(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def stream_rows(day: date) -> Iterator[Dict[str, str]]:
    """Yield the rows of one day's markets.csv without saving the file."""
    req = urllib.request.Request(BASE.format(day=day.isoformat()), headers={"User-Agent": "novigapi-python-examples"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as exc:
        print("  {}: HTTP {}, skipped".format(day, exc.code), file=sys.stderr)
        return
    with resp:
        for row in csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", newline="")):
            yield row


def pct(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        p = float(value) / 100.0
    except ValueError:
        return None
    return p if 0.0 < p < 1.0 else None


def league_of(ticker: str) -> str:
    head = (ticker or "").split("-", 1)[0]
    return head or "UNKNOWN"


def load_bets(path: str) -> Dict[str, float]:
    """market_id,entry_price (probability 0-1, or a percentage above 1)."""
    out: Dict[str, float] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            p = float(row["entry_price"])
            out[row["market_id"]] = p / 100.0 if p > 1.0 else p
    return out


def load_results(path: str) -> Dict[str, int]:
    with open(path, newline="") as fh:
        return {row["market_id"]: int(row["won"]) for row in csv.DictReader(fh)}


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


BUCKETS = [(-100.0, -5.0, "down 5+ pp"), (-5.0, -1.0, "down 1-5 pp"), (-1.0, 1.0, "flat (< 1 pp)"),
           (1.0, 5.0, "up 1-5 pp"), (5.0, 100.0, "up 5+ pp")]


def report_martingale(closes: Dict[str, List[float]], volume: Dict[str, float], min_volume: float) -> None:
    pairs = []
    for mid, xs in closes.items():
        if len(xs) < 3 or volume[mid] < min_volume:
            continue
        diffs = [(b - a) * 100.0 for a, b in zip(xs, xs[1:])]
        pairs.extend(zip(diffs, diffs[1:]))
    print("\nMartingale test: {} pairs of consecutive daily close-to-close changes.".format(len(pairs)))
    if len(pairs) < 2:
        return
    n = len(pairs)
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    vx = sum((a - mx) ** 2 for a, _ in pairs)
    vy = sum((b - my) ** 2 for _, b in pairs)
    corr = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else float("nan")
    print("Correlation of day-t change with day-t+1 change: {:+.3f}".format(corr))
    print("{:<16} {:>8} {:>16}".format("day-t move", "pairs", "mean next move"))
    for lo, hi, label in BUCKETS:
        nxt = [b for a, b in pairs if lo <= a < hi]
        if nxt:
            print("{:<16} {:>8} {:>+15.2f}p".format(label, len(nxt), sum(nxt) / len(nxt)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2026-08-04", help="first day, YYYY-MM-DD")
    parser.add_argument("--end", default=(date.today() - timedelta(days=1)).isoformat(), help="last day, YYYY-MM-DD")
    parser.add_argument("--bets", help="CSV of market_id,entry_price; default entry is the opening print")
    parser.add_argument("--results", help="CSV of market_id,won to score open vs close")
    parser.add_argument("--min-volume", type=float, default=100.0, help="skip markets with less total volume (dollars)")
    parser.add_argument("--include-combos", action="store_true")
    parser.add_argument("--out", help="write one row per market to this CSV")
    parser.add_argument("--martingale", action="store_true", help="test whether daily moves predict the next day's")
    args = parser.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    bets = load_bets(args.bets) if args.bets else {}
    results = load_results(args.results) if args.results else {}

    first_open: Dict[str, float] = {}
    first_day: Dict[str, str] = {}
    last_close: Dict[str, float] = {}
    last_day: Dict[str, str] = {}
    ticker: Dict[str, str] = {}
    volume: Dict[str, float] = defaultdict(float)
    closes: Dict[str, List[float]] = defaultdict(list)
    rows_read = 0

    for day in days(start, end):
        n = 0
        for row in stream_rows(day):
            n += 1
            mid = row.get("marketId") or ""
            t = row.get("reportTicker") or ""
            if not mid or (not args.include_combos and t.startswith("COMBO")):
                continue
            ticker[mid] = t
            try:
                volume[mid] += float(row.get("dailyVolume") or 0.0)
            except ValueError:
                pass
            o, c = pct(row.get("open", "")), pct(row.get("close", ""))
            if o is not None and mid not in first_open:
                first_open[mid], first_day[mid] = o, row.get("date") or day.isoformat()
            if c is not None:
                last_close[mid], last_day[mid] = c, row.get("date") or day.isoformat()
                if args.martingale:
                    closes[mid].append(c)
        rows_read += n
        print("  {}: {} rows".format(day, n), file=sys.stderr)

    by_league: Dict[str, List[float]] = defaultdict(list)
    scored = {"open_brier": 0.0, "close_brier": 0.0, "open_ll": 0.0, "close_ll": 0.0, "n": 0}
    out_rows = []
    for mid, close in last_close.items():
        entry = bets.get(mid) if bets else first_open.get(mid)
        if entry is None or volume[mid] < args.min_volume:
            continue
        clv_pp = (close - entry) * 100.0
        lg = league_of(ticker[mid])
        by_league[lg].append(clv_pp)
        by_league["ALL"].append(clv_pp)
        y = results.get(mid)
        if y is not None:
            scored["open_brier"] += brier(entry, y)
            scored["close_brier"] += brier(close, y)
            scored["open_ll"] += logloss(entry, y)
            scored["close_ll"] += logloss(close, y)
            scored["n"] += 1
        out_rows.append({"market_id": mid, "report_ticker": ticker[mid], "entry": round(entry, 4),
                         "entry_day": first_day.get(mid, ""), "close": round(close, 4), "close_day": last_day[mid],
                         "clv_pp": round(clv_pp, 2), "volume": round(volume[mid], 2),
                         "won": "" if y is None else y})

    print("\nNovig daily CSVs {} to {}: {} rows read, {} markets with an entry and a close (volume >= ${:.0f}).".format(
        start, end, rows_read, len(by_league.get("ALL", [])), args.min_volume))
    print("Entry = {}.\n".format("your --bets price" if bets else "first opening print"))
    header = "{:<10} {:>8} {:>10} {:>12} {:>10} {:>10} {:>10}".format(
        "league", "markets", "mean CLV", "mean |move|", ">= 1 pp", ">= 5 pp", "CLV > 0")
    print(header)
    print("-" * len(header))
    for lg in sorted(by_league, key=lambda k: (k != "ALL", -len(by_league[k]))):
        xs = by_league[lg]
        n = len(xs)
        print("{:<10} {:>8} {:>+9.2f}p {:>11.2f}p {:>10.1%} {:>10.1%} {:>10.1%}".format(
            lg, n, sum(xs) / n, sum(abs(x) for x in xs) / n,
            sum(abs(x) >= 1 for x in xs) / n, sum(abs(x) >= 5 for x in xs) / n, sum(x > 0 for x in xs) / n))

    if scored["n"]:
        n = scored["n"]
        print("\nScored against {} results: Brier open {:.4f} vs close {:.4f}; log loss open {:.4f} vs close {:.4f}.".format(
            n, scored["open_brier"] / n, scored["close_brier"] / n, scored["open_ll"] / n, scored["close_ll"] / n))

    if args.martingale:
        report_martingale(closes, volume, args.min_volume)

    if args.out and out_rows:
        with open(args.out, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
            writer.writeheader()
            writer.writerows(out_rows)
        print("\nWrote {} rows to {}.".format(len(out_rows), args.out))


if __name__ == "__main__":
    main()
