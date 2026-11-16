# Novig API for Python: novigapi

A Novig API Python client for read-only Novig market data. `pip install novigapi` and read open Novig markets, player props, intraday line history and no-vig fair prices, plus devig helpers you can run offline.

[Website](https://novigapi.com/?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) | [Docs](https://novigapi.com/docs?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) | [Free API key](https://novigapi.com/sign-up?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) | [Pricing](https://novigapi.com/pricing?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) | [All SDKs](https://novigapi.com/sdks?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python)

Also for novigapi.com: [JavaScript: `npm install novigapi`](https://github.com/novigapi/novigapi-js) | [MCP server: `npx -y novigapi-mcp`](https://github.com/novigapi/novigapi-mcp)

A small Python client for [novigapi.com](https://novigapi.com/?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python), a read-only Novig market data API, plus pure-Python devig helpers and three runnable examples.

Novig has an official trading API and free daily CSVs. novigapi.com is the read-only data layer on top: no account, names resolved, intraday line history, fair prices and alerts. This package talks to novigapi.com. To place orders or read a Novig account, use the official Novig API documented at [docs.novig.com](https://docs.novig.com).

Independent. Not affiliated with, endorsed by or sponsored by Novig.

- Standard library only (`urllib`, `json`). Python 3.8 or later. No dependencies.
- MIT licensed.

## Install

```bash
pip install novigapi
```

On PyPI: https://pypi.org/project/novigapi/ . Source: https://github.com/novigapi/novigapi-python

Tests need no key, no network and no pytest: `python3 tests/run.py` (pytest also works).

## Quickstart

Get a free key at [novigapi.com/sign-up](https://novigapi.com/sign-up?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) (Free plan: 100 credits a month, 20 requests a minute), then:

```bash
export NOVIGAPI_KEY=nv_...
```

```python
from novigapi import NovigAPI, devig, prob_to_american

api = NovigAPI()  # reads NOVIGAPI_KEY

page = api.markets(league="NFL", status="open", limit=20)
for market in page["data"]:
    print(market["market_id"], market.get("description"))

fair = api.fair_price(page["data"][0]["market_id"])
print(fair["data"], fair["meta"].get("formula"))

# Devig any two prices (probabilities from 0 to 1)
print(devig([0.5238, 0.5238], "shin"))        # [0.5, 0.5]
print(prob_to_american(0.40))                  # 150.0
```

Every method returns the JSON envelope `{"data": ..., "meta": {...}}`. List endpoints page with `cursor`; `api.iter_rows("markets", league="NBA")` follows `meta.next_cursor` for you.

### Methods

| Method | Endpoint |
|---|---|
| `markets(league, event_id, market_type, player, team, status, limit, cursor)` | `GET /markets` |
| `events(league, status, limit, cursor)` | `GET /events` |
| `market(market_id)` | `GET /markets/{id}` |
| `orderbook(market_id)` | `GET /orderbook/{id}` |
| `trades(market_id, since, limit, cursor)` | `GET /trades` |
| `ohlc_daily(market_id, date)` | `GET /ohlc/daily` |
| `fair_price(market_id)` | `GET /fair-price` |
| `line_history(market_id or outcome_id, since, until)` | `GET /line-history` |
| `player_props(league, player)` | `GET /player-props` |
| `players(league, q)`, `teams(league)`, `leagues()` | `GET /players`, `/teams`, `/leagues` |
| `results(league, market_id, graded, since)` | `GET /results` |
| `market_summary(date, since, league, market_type, kind)` | `GET /market-summary/daily` |
| `ev(league, min_edge, min_prob, books, sort, ...)` | `GET /ev` (FanDuel and DraftKings vs the Novig fair price) |
| `arbitrage(type, league, min_profit)` | `GET /arbitrage` (Production and up) |
| `compare(market_id)` | `GET /compare/{market_id}` |
| `bulk_csv(dataset, ...)` | `GET /bulk/csv` (Production and up), returns CSV text |
| `clv(market_id, player, league, date, settled, since, until)` | `GET /clv` |
| `line_moves(league, market_id, kind, since, min_delta_pp)` | `GET /line-moves` |

Base URL `https://novigapi.com/api/v1`. Auth header `Authorization: Bearer nv_...`. Full reference: [novigapi.com/docs](https://novigapi.com/docs?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python).

### Errors and limits

Any non-2xx response raises `NovigAPIError` with `status`, `code` and `message`. A 429 raises `RateLimitError`, which also carries the fields from the 429 body:

```python
from novigapi import NovigAPI, RateLimitError
import time

api = NovigAPI()
try:
    api.markets(league="NBA")
except RateLimitError as err:
    print(err.code, err.plan, err.limit, err.reset_at, err.upgrade_url)
    if err.code == "RATE_LIMITED" and err.retry_after:
        time.sleep(err.retry_after)
```

`RATE_LIMITED` is the per-minute limit and sends `Retry-After`. `QUOTA_EXCEEDED` means the month's credits are used; there are no automatic overage charges.

## Devig helpers

`novigapi.devig` has four methods as pure functions with docstrings: `multiplicative`, `additive`, `power` and `shin`, plus `american_to_prob`, `prob_to_american`, `decimal_to_prob`, `prob_to_decimal`, `overround` and `hold`. `novigapi.taker_fee(price, contracts, coefficient=0.06)` returns Novig's taker fee, `coefficient x p x (1 - p) x contracts`, per [docs.novig.com](https://docs.novig.com/fees.md) (checked 12 Nov 2026).

Worked example, -300 / +240 (implied 75.00% and 29.41%, 4.41% overround):

| Method | Favourite | Longshot |
|---|---|---|
| Multiplicative | 71.83% (-255) | 28.17% (+255) |
| Additive | 72.79% (-268) | 27.21% (+268) |
| Power | 73.31% (-275) | 26.69% (+275) |
| Shin | 72.79% (-268) | 27.21% (+268) |

With two outcomes, Shin and additive agree. The [no-vig calculator](https://novigapi.com/no-vig-calculator?utm_source=github&utm_medium=readme&utm_campaign=novigapi-python) runs the same four methods in the browser.

## Examples

```bash
python examples/devig_board.py --league NFL --method shin     # devig every two-sided market in a league
python examples/arb_scanner.py --league NBA                   # combined price below $1 after the taker fee
python examples/clv_backtest.py --start 2026-08-04 --end 2026-11-11   # no key needed
```

- `devig_board.py` lists open two-way markets for a league and prints the fair probability and fair American odds of each side.
- `arb_scanner.py` adds the taker fee to each leg, `0.06 x p x (1 - p)` per $1 of payout (pregame game-market fills are fee-free; the default charges every leg, the conservative case), and reports any pair that costs less than $1. Pass `--other prices.csv` to pair a Novig side with a price you collected from another venue.
- `clv_backtest.py` streams Novig's own daily `markets.csv` files from `https://data.novig.com/reporting/trade-data/<date>/markets.csv` and compares an entry price (the opening print, or yours via `--bets`) with the `close` column. It needs no API key and saves nothing to disk. Pass `--results` with `market_id,won` to score open against close with the Brier score, or `--martingale` to test, without any results, whether one day's move predicts the next day's.

Tests:

```bash
pip install -e ".[test]"
pytest tests -q
```

## Data notes

- Prices are probabilities. Novig shows them as percentages: 54% is 0.54.
- Novig's book holds bids only. The ask on an outcome is 1 minus the best bid on the other outcome.
- REST data on paid plans is at most about 10 seconds old; the stream pushes changes within 5 to 30 seconds.
- Novig's daily CSVs start in early August 2026 and carry no player or team names; novigapi.com joins the names.

## License

MIT. Copyright (c) 2026 Stunning Couches LLC.

Independent. Not affiliated with, endorsed by or sponsored by Novig.
