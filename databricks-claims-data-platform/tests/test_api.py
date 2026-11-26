"""Tests for the claims read API: pagination, filters, lookups, gold endpoints."""
import json
import threading
import urllib.request

import pytest

from claims_platform.api import run_server
from claims_platform.pipeline import run as run_claims

BASE = None


@pytest.fixture(scope="module", autouse=True)
def server():
    run_claims()  # build lakehouse/ so the API has data to serve
    srv = run_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    global BASE
    BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    yield
    srv.shutdown()


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def test_health():
    status, body = get("/health")
    assert status == 200 and body["status"] == "ok"


def test_claims_list_paginates():
    status, body = get("/claims?limit=10&offset=0")
    assert status == 200
    assert body["total"] == 296
    assert len(body["rows"]) == 10
    _, body2 = get("/claims?limit=10&offset=10")
    assert body2["rows"][0]["claim_id"] != body["rows"][0]["claim_id"]


def test_claims_limit_capped():
    _, body = get("/claims?limit=5000")
    assert body["limit"] == 500
    assert len(body["rows"]) == 296


def test_claims_filter_by_plan():
    _, body = get("/claims?plan=Medicaid&limit=500")
    assert body["total"] > 0
    assert all(r["plan"] == "Medicaid" for r in body["rows"])


def test_claim_lookup_and_404():
    _, body = get("/claims?limit=1")
    claim_id = body["rows"][0]["claim_id"]
    status, hit = get(f"/claims/{claim_id}")
    assert status == 200 and hit["claim_id"] == claim_id
    with pytest.raises(urllib.error.HTTPError) as exc:
        get("/claims/C99999")
    assert exc.value.code == 404


def test_member_lookup():
    _, body = get("/claims?limit=1")
    member_id = body["rows"][0]["member_id"]
    status, hit = get(f"/members/{member_id}")
    assert status == 200 and hit["member_id"] == member_id
    assert hit["plan"] in {"Medicare Advantage", "Medicaid",
                           "Commercial PPO", "Commercial HMO"}


def test_gold_daily_endpoint():
    status, body = get("/gold/daily?limit=500")
    assert status == 200 and body["total"] > 0
    assert all("total_paid" in r and "claim_count" in r for r in body["rows"])
    date = body["rows"][0]["service_date"]
    _, filtered = get(f"/gold/daily?service_date={date}&limit=500")
    assert all(r["service_date"] == date for r in filtered["rows"])


def test_gold_monthly_endpoint():
    status, body = get("/gold/monthly?limit=500")
    assert status == 200 and body["total"] > 0
    assert sum(r["claim_count"] for r in body["rows"]) == 296


def test_unknown_endpoint_404():
    with pytest.raises(urllib.error.HTTPError) as exc:
        get("/nope")
    assert exc.value.code == 404
