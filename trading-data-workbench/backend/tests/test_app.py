"""End-to-end tests for the trading data workbench API.

Starts the real HTTP server on an ephemeral port and exercises it over
urllib — instruments, quotes, order validation, idempotency, fills,
positions, and the data-quality report.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from trading_workbench.app import Handler


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(base_url, path):
    with urllib.request.urlopen(base_url + path) as resp:
        return resp.status, json.loads(resp.read().decode())


def post(base_url, path, payload, headers=None):
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_health(base_url):
    status, body = get(base_url, "/health")
    assert status == 200
    assert body["status"] == "ok"


def test_instruments_lists_eight(base_url):
    status, body = get(base_url, "/api/instruments")
    assert status == 200
    symbols = [i["symbol"] for i in body["instruments"]]
    assert symbols == ["AAPL", "GLD", "JPM", "MSFT", "NVDA", "SPY", "TLT", "XOM"]
    aapl = next(i for i in body["instruments"] if i["symbol"] == "AAPL")
    assert aapl["asset_class"] == "Equity"
    assert aapl["exchange"] == "NASDAQ"


def test_instrument_detail_and_unknown(base_url):
    status, body = get(base_url, "/api/instruments/MSFT")
    assert status == 200
    assert body["symbol"] == "MSFT"
    assert body["latest_quote"]["symbol"] == "MSFT"
    assert body["latest_quote"]["bid"] <= body["latest_quote"]["ask"]
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/instruments/NOPE")
    assert exc.value.code == 404


def test_quotes_ordered_and_valid(base_url):
    status, body = get(base_url, "/api/quotes?symbol=AAPL")
    assert status == 200
    quotes = body["quotes"]
    assert len(quotes) == 60
    timestamps = [q["ts"] for q in quotes]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 60
    for q in quotes:
        assert q["bid"] <= q["last"] <= q["ask"]
        assert q["bid"] > 0 and q["volume"] >= 0


def test_quotes_limit_and_errors(base_url):
    status, body = get(base_url, "/api/quotes?symbol=JPM&limit=5")
    assert status == 200
    assert len(body["quotes"]) == 5
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/quotes?symbol=NOPE")
    assert exc.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/quotes?symbol=AAPL&limit=0")
    assert exc.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/quotes")
    assert exc.value.code == 400


def test_market_buy_fills_and_position(base_url):
    status, order = post(base_url, "/api/orders",
                         {"symbol": "AAPL", "side": "BUY", "qty": 10})
    assert status == 201
    assert order["status"] == "filled"
    assert order["filled_qty"] == 10
    assert order["filled_price"] > 0
    status, body = get(base_url, "/api/positions")
    assert status == 200
    aapl = next(p for p in body["positions"] if p["symbol"] == "AAPL")
    assert aapl["qty"] == 10
    assert aapl["avg_cost"] == order["filled_price"]
    assert aapl["market_value"] == round(10 * aapl["last_price"], 2)
    assert aapl["unrealized_pnl"] == round(aapl["market_value"] - 10 * aapl["avg_cost"], 2)


def test_order_validation_errors(base_url):
    for payload in (
        {"symbol": "AAPL", "side": "HOLD", "qty": 1},
        {"symbol": "AAPL", "side": "BUY", "qty": 0},
        {"symbol": "AAPL", "side": "BUY", "qty": 1.5},
        {"symbol": "AAPL", "side": "BUY"},
        {"symbol": "NOPE", "side": "BUY", "qty": 1},
        {"symbol": "AAPL", "side": "BUY", "qty": 1, "order_type": "LIMIT"},
        {"symbol": "AAPL", "side": "BUY", "qty": 1, "limit_price": 100.0},
    ):
        status, body = post(base_url, "/api/orders", payload)
        assert status == 400, payload
        assert "error" in body


def test_idempotent_replay_returns_original(base_url):
    headers = {"Idempotency-Key": "test-key-msft-1"}
    status, first = post(base_url, "/api/orders",
                         {"symbol": "MSFT", "side": "BUY", "qty": 5}, headers)
    assert status == 201
    status, second = post(base_url, "/api/orders",
                          {"symbol": "MSFT", "side": "BUY", "qty": 5}, headers)
    assert status == 200
    assert second["id"] == first["id"]
    status, body = get(base_url, "/api/orders")
    matches = [o for o in body["orders"] if o.get("idempotency_key") == "test-key-msft-1"]
    assert len(matches) == 1


def test_sell_more_than_held_rejected(base_url):
    status, body = post(base_url, "/api/orders",
                        {"symbol": "NVDA", "side": "SELL", "qty": 3})
    assert status == 422
    assert "only 0 held" in body["error"]


def test_limit_order_open_then_fills_on_cross(base_url):
    status, body = get(base_url, "/api/instruments/NVDA")
    mid = body["latest_quote"]["last"]
    status, order = post(base_url, "/api/orders",
                         {"symbol": "NVDA", "side": "BUY", "qty": 2,
                          "order_type": "LIMIT", "limit_price": round(mid * 0.5, 2)})
    assert status == 201
    assert order["status"] == "open"
    assert order["filled_qty"] == 0
    status, order = post(base_url, "/api/orders",
                         {"symbol": "NVDA", "side": "BUY", "qty": 2,
                          "order_type": "LIMIT", "limit_price": round(mid * 1.5, 2)})
    assert order["status"] == "filled"


def test_sell_reduces_position(base_url):
    post(base_url, "/api/orders", {"symbol": "XOM", "side": "BUY", "qty": 20})
    status, order = post(base_url, "/api/orders",
                         {"symbol": "XOM", "side": "SELL", "qty": 8})
    assert status == 201
    assert order["status"] == "filled"
    _, body = get(base_url, "/api/positions")
    xom = next(p for p in body["positions"] if p["symbol"] == "XOM")
    assert xom["qty"] == 12


def test_order_lookup_and_unknown(base_url):
    status, order = post(base_url, "/api/orders",
                         {"symbol": "SPY", "side": "BUY", "qty": 1})
    status, body = get(base_url, f"/api/orders/{order['id']}")
    assert status == 200
    assert body["symbol"] == "SPY"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/orders/999999")
    assert exc.value.code == 404


def test_malformed_json_rejected(base_url):
    req = urllib.request.Request(
        base_url + "/api/orders", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_data_quality_report_clean(base_url):
    status, body = get(base_url, "/api/data-quality")
    assert status == 200
    assert len(body["report"]) == 8
    for entry in body["report"]:
        assert entry["rows_checked"] == 60
        assert entry["issues"] == [], entry["symbol"]


def test_metrics_endpoint(base_url):
    with urllib.request.urlopen(base_url + "/metrics") as resp:
        assert resp.status == 200
        text = resp.read().decode()
    assert "uptime_seconds" in text
    assert "http_requests_total" in text


def test_unknown_route_404(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + "/api/nope")
    assert exc.value.code == 404
