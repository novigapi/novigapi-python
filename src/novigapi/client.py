"""HTTP client for the novigapi.com REST API (read-only Novig market data).

Standard library only: urllib for HTTP, json for parsing.

Every method returns the parsed JSON envelope, a dict shaped like

    {"data": [...] or {...}, "meta": {"next_cursor": ..., "limit": ..., "count": ...}}

List endpoints page with ``cursor``: pass ``meta["next_cursor"]`` from the
previous page, or use ``iter_rows`` to walk every page.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, Optional

from . import __version__

DEFAULT_BASE_URL = "https://novigapi.com/api/v1"
Json = Dict[str, Any]

__all__ = ["NovigAPI", "NovigAPIError", "RateLimitError", "DEFAULT_BASE_URL"]


class NovigAPIError(Exception):
    """Any non-2xx response. Carries the API's error code, message and HTTP status."""

    def __init__(self, status: int, code: str, message: str, body: Optional[Json] = None, headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__("{} {}: {}".format(status, code, message))
        self.status = status
        self.code = code
        self.message = message
        self.body = body or {}
        self.headers = headers or {}


class RateLimitError(NovigAPIError):
    """HTTP 429: the per-minute rate limit (RATE_LIMITED) or the monthly credits (QUOTA_EXCEEDED).

    Fields from the 429 body are copied onto the exception:
    plan, limit, reset_at (ISO 8601), upgrade_url, and retry_after (seconds, from the
    Retry-After header, set on RATE_LIMITED only).
    """

    def __init__(self, status: int, code: str, message: str, body: Optional[Json] = None, headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status, code, message, body, headers)
        err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
        self.plan: Optional[str] = err.get("plan")
        self.limit: Optional[int] = err.get("limit")
        self.reset_at: Optional[str] = err.get("reset_at")
        self.upgrade_url: Optional[str] = err.get("upgrade_url")
        retry = (headers or {}).get("retry-after")
        self.retry_after: Optional[int] = int(retry) if retry and retry.isdigit() else None

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.plan:
            parts.append("plan={}".format(self.plan))
        if self.limit is not None:
            parts.append("limit={}".format(self.limit))
        if self.reset_at:
            parts.append("reset_at={}".format(self.reset_at))
        if self.retry_after is not None:
            parts.append("retry_after={}s".format(self.retry_after))
        if self.upgrade_url:
            parts.append("upgrade_url={}".format(self.upgrade_url))
        return " ".join(parts)


class NovigAPI:
    """Client for https://novigapi.com/api/v1.

    >>> api = NovigAPI()                      # reads NOVIGAPI_KEY from the environment
    >>> page = api.markets(league="NFL", status="open", limit=50)
    >>> for market in page["data"]:
    ...     print(market["market_id"], market.get("description"))
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        key = api_key or os.environ.get("NOVIGAPI_KEY")
        if not key:
            raise ValueError("No API key. Set NOVIGAPI_KEY or pass api_key='nv_...'. Free keys: https://novigapi.com/sign-up")
        if not key.startswith("nv_"):
            raise ValueError("novigapi.com keys start with nv_")
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ----- transport -------------------------------------------------------

    def get(self, path: str, **params: Any) -> Json:
        """GET a path under the base URL. None-valued params are dropped."""
        query = {k: _param(v) for k, v in params.items() if v is not None}
        url = self.base_url + "/" + path.lstrip("/")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self.api_key,
            "Accept": "application/json",
            "User-Agent": "novigapi-python/" + __version__,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            raise _error_from(exc) from None

    def _raw(self, path: str) -> str:
        req = urllib.request.Request(self.base_url + "/" + path, headers={
            "Authorization": "Bearer " + self.api_key, "Accept": "text/csv", "User-Agent": "novigapi-python/" + __version__,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise _error_from(exc) from None

    def iter_rows(self, path: str, max_pages: Optional[int] = None, **params: Any) -> Iterator[Json]:
        """Yield every row of a list endpoint, following meta.next_cursor."""
        cursor = params.pop("cursor", None)
        pages = 0
        while True:
            page = self.get(path, cursor=cursor, **params)
            data = page.get("data") or []
            for row in data if isinstance(data, list) else [data]:
                yield row
            pages += 1
            cursor = (page.get("meta") or {}).get("next_cursor")
            if not cursor or (max_pages is not None and pages >= max_pages):
                return

    # ----- markets and events ---------------------------------------------

    def markets(self, league: Optional[str] = None, event_id: Optional[str] = None, market_type: Optional[str] = None,
                player: Optional[str] = None, team: Optional[str] = None, status: Optional[str] = None,
                limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /markets. status: open, closed, settled, suspended or all."""
        return self.get("markets", league=league, event_id=event_id, market_type=market_type, player=player,
                        team=team, status=status, limit=limit, cursor=cursor)

    def events(self, league: Optional[str] = None, status: Optional[str] = None,
               limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /events."""
        return self.get("events", league=league, status=status, limit=limit, cursor=cursor)

    def market(self, market_id: str) -> Json:
        """GET /markets/{id}: one market with its outcomes."""
        return self.get("markets/" + _path_id(market_id))

    def orderbook(self, market_id: str) -> Json:
        """GET /orderbook/{id}: the current book. Novig holds bids only; the ask on an
        outcome is 1 minus the best bid on the other outcome."""
        return self.get("orderbook/" + _path_id(market_id))

    # ----- prices and history ---------------------------------------------

    def trades(self, market_id: Optional[str] = None, since: Optional[str] = None,
               limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /trades. since: ISO 8601 date or time."""
        return self.get("trades", market_id=market_id, since=since, limit=limit, cursor=cursor)

    def ohlc_daily(self, market_id: Optional[str] = None, date: Optional[str] = None,
                   limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /ohlc/daily. Send market_id, date (YYYY-MM-DD) or both."""
        if not market_id and not date:
            raise ValueError("send market_id or date")
        return self.get("ohlc/daily", market_id=market_id, date=date, limit=limit, cursor=cursor)

    def fair_price(self, market_id: str) -> Json:
        """GET /fair-price: the two-sided mid, fair_yes = (bid_yes + (1 - bid_no)) / 2."""
        return self.get("fair-price", market_id=market_id)

    def line_history(self, market_id: Optional[str] = None, outcome_id: Optional[str] = None,
                     since: Optional[str] = None, until: Optional[str] = None,
                     limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /line-history: intraday price ticks for a market or one outcome."""
        if not market_id and not outcome_id:
            raise ValueError("send market_id or outcome_id")
        return self.get("line-history", market_id=market_id, outcome_id=outcome_id, since=since, until=until,
                        limit=limit, cursor=cursor)

    def line_moves(self, league: Optional[str] = None, market_id: Optional[str] = None, kind: Optional[str] = None,
                   since: Optional[str] = None, min_delta_pp: Optional[float] = None, limit: Optional[int] = None,
                   cursor: Optional[str] = None) -> Json:
        """GET /line-moves. kind: move or steam. min_delta_pp: smallest move to return, in percentage points."""
        return self.get("line-moves", league=league, market_id=market_id, kind=kind, since=since,
                        min_delta_pp=min_delta_pp, limit=limit, cursor=cursor)

    def clv(self, market_id: Optional[str] = None, player: Optional[str] = None, league: Optional[str] = None,
            date: Optional[str] = None, settled: Optional[bool] = None, since: Optional[str] = None,
            until: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /clv: each outcome's open_fair and close_fair before the start, clv_pp, and won once graded."""
        if not any([market_id, player, league, date]):
            raise ValueError("send market_id, player, league or date")
        return self.get("clv", market_id=market_id, player=player, league=league, date=date, settled=settled,
                        since=since, until=until, limit=limit, cursor=cursor)

    def results(self, league: Optional[str] = None, market_id: Optional[str] = None, graded: Optional[bool] = None,
                since: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /results: settled markets with the winning outcome where known."""
        return self.get("results", league=league, market_id=market_id, graded=graded, since=since, limit=limit, cursor=cursor)

    def market_summary(self, date: Optional[str] = None, since: Optional[str] = None, league: Optional[str] = None,
                       market_type: Optional[str] = None, kind: Optional[str] = None,
                       limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /market-summary/daily: straight markets and parlays (COMBO) per day from Novig's daily files."""
        return self.get("market-summary/daily", date=date, since=since, league=league, market_type=market_type,
                        kind=kind, limit=limit, cursor=cursor)

    # ----- cross-venue: FanDuel and DraftKings against the Novig fair price ------

    def ev(self, league: Optional[str] = None, market_type: Optional[str] = None, min_edge: Optional[float] = None,
           books: Optional[str] = None, min_prob: Optional[float] = None, alt_lines: Optional[bool] = None,
           confidence: Optional[str] = None, sort: Optional[str] = None, player: Optional[str] = None,
           market_id: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /ev: book prices that pay more than the Novig fair probability. ev_pct = (fair x decimal - 1) x 100."""
        return self.get("ev", league=league, market_type=market_type, min_edge=min_edge, books=books, min_prob=min_prob,
                        alt_lines=alt_lines, confidence=confidence, sort=sort, player=player, market_id=market_id,
                        limit=limit, cursor=cursor)

    def arbitrage(self, type: Optional[str] = None, league: Optional[str] = None, market_type: Optional[str] = None,
                  min_profit: Optional[float] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /arbitrage: two-way arbitrage across Novig, FanDuel and DraftKings, or type="middles". Production and up."""
        return self.get("arbitrage", type=type, league=league, market_type=market_type, min_profit=min_profit,
                        limit=limit, cursor=cursor)

    def compare(self, market_id: str) -> Json:
        """GET /compare/{market_id}: one Novig market beside each book on exactly the same line."""
        return self.get("compare/" + _path_id(market_id))

    def bulk_csv(self, dataset: str, market_id: Optional[str] = None, league: Optional[str] = None,
                 since: Optional[str] = None, date: Optional[str] = None, limit: Optional[int] = None,
                 cursor: Optional[str] = None) -> str:
        """GET /bulk/csv: CSV text for a dataset such as line_moves. Production and up."""
        query = {k: _param(v) for k, v in dict(dataset=dataset, market_id=market_id, league=league, since=since,
                                                date=date, limit=limit, cursor=cursor).items() if v is not None}
        return self._raw("bulk/csv?" + urllib.parse.urlencode(query))

    # ----- names ----------------------------------------------------------

    def player_props(self, league: str, player: str, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /player-props. player is a slug, such as lebron-james."""
        return self.get("player-props", league=league, player=player, limit=limit, cursor=cursor)

    def players(self, league: Optional[str] = None, q: Optional[str] = None,
                limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /players. q: name search, up to 80 characters."""
        return self.get("players", league=league, q=q, limit=limit, cursor=cursor)

    def teams(self, league: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /teams."""
        return self.get("teams", league=league, limit=limit, cursor=cursor)

    def leagues(self, limit: Optional[int] = None, cursor: Optional[str] = None) -> Json:
        """GET /leagues."""
        return self.get("leagues", limit=limit, cursor=cursor)


def _param(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _path_id(value: str) -> str:
    if not value:
        raise ValueError("id is required")
    return urllib.parse.quote(value, safe="")


def _error_from(exc: urllib.error.HTTPError) -> NovigAPIError:
    headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        body = {}
    err = body.get("error", {}) if isinstance(body, dict) else {}
    code = str(err.get("code") or "HTTP_{}".format(exc.code))
    message = str(err.get("message") or exc.reason or "request failed")
    cls = RateLimitError if exc.code == 429 else NovigAPIError
    return cls(exc.code, code, message, body if isinstance(body, dict) else {}, headers)
