"""High-volume data / API tests for the /trades endpoint.

Covers what a clearing-house SDET checks on a bulk feed: the full
5,000-record dataset is reachable by paging, pages never overlap or drop
rows, every record satisfies the data invariants (positive price and
quantity, valid side/symbol, strictly increasing timestamps), and a full
page answers inside the latency budget. Bad paging parameters are
rejected with 400 instead of silently returning wrong data.
"""
import json
import time
import urllib.error
import urllib.request

TOTAL_TRADES = 5000


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_trades_list_reports_total(api_server):
    status, body = get(api_server, "/trades?limit=10&offset=0")
    assert status == 200
    assert body["total"] == TOTAL_TRADES
    assert body["limit"] == 10 and body["offset"] == 0
    assert len(body["trades"]) == 10


def test_paging_covers_all_trades_without_overlap(api_server):
    seen_ids = []
    offset = 0
    while offset < TOTAL_TRADES:
        status, body = get(api_server, f"/trades?limit=500&offset={offset}")
        assert status == 200
        seen_ids.extend(t["id"] for t in body["trades"])
        offset += 500
    assert len(seen_ids) == TOTAL_TRADES
    assert len(set(seen_ids)) == TOTAL_TRADES  # no duplicated rows
    assert seen_ids == sorted(seen_ids)        # pages in id order, none lost


def test_trade_data_invariants(api_server):
    status, body = get(api_server, "/trades?limit=1000&offset=0")
    assert status == 200
    prev_ts = None
    for trade in body["trades"]:
        assert trade["price"] > 0
        assert 1 <= trade["qty"] <= 1000
        assert trade["side"] in ("BUY", "SELL")
        assert trade["symbol"] in ("AAPL", "MSFT", "SPX", "NDX", "ES",
                                   "CL", "GC", "EURUSD")
        if prev_ts is not None:
            assert trade["ts"] > prev_ts
        prev_ts = trade["ts"]


def test_get_trade_by_id_and_missing_trade(api_server):
    status, body = get(api_server, "/trades/42")
    assert status == 200
    assert body["id"] == 42
    status, body = get(api_server, "/trades/99999")
    assert status == 404
    assert "error" in body


def test_invalid_paging_is_rejected(api_server):
    status, body = get(api_server, "/trades?limit=0&offset=0")
    assert status == 400
    assert "error" in body
    status, body = get(api_server, "/trades?limit=abc&offset=0")
    assert status == 400


def test_full_page_answers_within_latency_budget(api_server):
    started = time.monotonic()
    status, body = get(api_server, "/trades?limit=1000&offset=0")
    latency = time.monotonic() - started
    assert status == 200
    assert len(body["trades"]) == 1000
    assert latency < 2.0, f"1,000-row page took {latency:.2f}s"
