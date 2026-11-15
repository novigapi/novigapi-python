"""Client tests with a stubbed transport: no network, no key needed."""
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from novigapi import NovigAPI, NovigAPIError, RateLimitError  # noqa: E402

CALLS = []


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub(pages):
    """Replace urlopen with one that returns each page in turn and records the request."""
    it = iter(pages)

    def fake(req, timeout=None):
        CALLS.append(req)
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return _Resp(json.dumps(nxt).encode())

    urllib.request.urlopen = fake


def _http_error(status, body, headers=None):
    from email.message import Message
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://novigapi.com/api/v1/x", status, "err", msg, io.BytesIO(json.dumps(body).encode()))


def test_key_rules():
    os.environ.pop("NOVIGAPI_KEY", None)
    try:
        NovigAPI()
        assert False, "expected ValueError"
    except ValueError as e:
        assert "NOVIGAPI_KEY" in str(e)
    try:
        NovigAPI(api_key="sk_wrong")
        assert False
    except ValueError:
        pass


def test_request_shape_and_paging():
    CALLS.clear()
    _stub([{"data": [{"market_id": "a"}], "meta": {"next_cursor": "c2"}}, {"data": [{"market_id": "b"}], "meta": {"next_cursor": None}}])
    api = NovigAPI(api_key="nv_test")
    rows = list(api.iter_rows("markets", league="NFL", status="open"))
    assert [r["market_id"] for r in rows] == ["a", "b"]
    first, second = CALLS
    assert first.full_url == "https://novigapi.com/api/v1/markets?league=NFL&status=open"
    assert second.full_url.endswith("cursor=c2&league=NFL&status=open") or "cursor=c2" in second.full_url
    assert first.headers["Authorization"] == "Bearer nv_test"


def test_cross_venue_and_clv_params():
    CALLS.clear()
    _stub([{"data": [], "meta": {}}] * 4)
    api = NovigAPI(api_key="nv_test")
    api.ev(league="NBA", min_edge=2, sort="ev", alt_lines=False)
    api.arbitrage(type="middles", league="NFL")
    api.compare("01a1/x")
    api.clv(league="NFL", date="2026-11-15", settled=True)
    urls = [c.full_url for c in CALLS]
    assert urls[0] == "https://novigapi.com/api/v1/ev?league=NBA&min_edge=2&alt_lines=false&sort=ev"
    assert urls[1] == "https://novigapi.com/api/v1/arbitrage?type=middles&league=NFL"
    assert urls[2] == "https://novigapi.com/api/v1/compare/01a1%2Fx"
    assert urls[3] == "https://novigapi.com/api/v1/clv?league=NFL&date=2026-11-15&settled=true"


def test_errors_are_typed():
    _stub([_http_error(429, {"error": {"code": "QUOTA_EXCEEDED", "message": "monthly credits used", "plan": "free", "limit": 100, "upgrade_url": "https://novigapi.com/upgrade"}}, {"Retry-After": "30"})])
    api = NovigAPI(api_key="nv_test")
    try:
        api.markets()
        assert False
    except RateLimitError as e:
        assert e.code == "QUOTA_EXCEEDED" and e.plan == "free" and e.limit == 100 and e.retry_after == 30
    _stub([_http_error(401, {"error": {"code": "INVALID_API_KEY", "message": "bad key"}})])
    try:
        api.markets()
        assert False
    except NovigAPIError as e:
        assert e.status == 401 and e.code == "INVALID_API_KEY"
