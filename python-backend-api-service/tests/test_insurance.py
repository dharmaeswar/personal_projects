"""Tests for the insurance policy-and-claims module.

Unit tests cover premium math, validation and the claim payout rule;
integration tests cover the new REST endpoints end to end.
"""

import http.client
import json
import threading
import time

import pytest

from payments_api.app import create_server
from payments_api.insurance import (
    EventPublisher,
    PolicyStore,
    QuoteCache,
    ValidationError,
    compute_premium_cents,
    validate_policy,
)
from payments_api.models import ValidationError as ModelValidationError


def _policy(**overrides):
    payload = {
        "policy_type": "auto",
        "coverage_limit_cents": 25_000_00,
        "deductible_cents": 500_00,
        "term_months": 12,
        "state": "NY",
        "holder_id": "holder_1",
    }
    payload.update(overrides)
    return payload


# --- premium math ---


def test_premium_auto_ny_12mo():
    # rate 500 bps - deductible credit (50000/2500000 = 200 bps) = 300 bps;
    # NY factor 110% -> 2,500,000 x 300 x 110 / 1,000,000 = 82,500 cents.
    assert compute_premium_cents(validate_policy(_policy())) == 82_500


def test_premium_6mo_term_is_half():
    assert compute_premium_cents(validate_policy(_policy(term_months=6))) == 41_250


def test_premium_home_lower_rate_and_default_state_factor():
    # home 320 bps - 200 bps credit = 120 bps; default factor 100%
    # -> 2,500,000 x 120 / 10,000 = 30,000 cents.
    assert compute_premium_cents(
        validate_policy(_policy(policy_type="home", state="OH"))
    ) == 30_000


def test_premium_deductible_credit_capped_and_rate_floored():
    # deductible = full coverage -> credit capped at 2000 bps; rate floored at 100.
    assert compute_premium_cents(
        validate_policy(_policy(deductible_cents=25_000_00, state="OH"))
    ) == 25_000


def test_validate_policy_rejects_bad_inputs():
    for bad in (
        _policy(policy_type="life"),
        _policy(coverage_limit_cents=50),
        _policy(deductible_cents=30_000_00),
        _policy(term_months=3),
        _policy(state="ny"),
        _policy(holder_id=""),
    ):
        with pytest.raises((ValidationError, ModelValidationError)):
            validate_policy(bad)


# --- store, cache, events ---


def test_policy_store_create_and_claim_payout():
    store = PolicyStore()
    policy = store.create_policy(validate_policy(_policy()))
    assert policy.id == "pol_000001"
    assert policy.premium_cents == 82_500
    claim = store.file_claim(policy, 200_000, "rear-end collision")
    assert claim.status == "filed"
    settled = store.settle_claim(claim, "approve")
    assert settled.status == "settled"
    assert settled.payout_cents == 150_000  # 200,000 - 50,000 deductible


def test_claim_above_coverage_rejected():
    store = PolicyStore()
    policy = store.create_policy(validate_policy(_policy()))
    with pytest.raises(ValidationError):
        store.file_claim(policy, 30_000_00, "total loss")


def test_claim_below_deductible_pays_zero():
    store = PolicyStore()
    policy = store.create_policy(validate_policy(_policy()))
    claim = store.file_claim(policy, 40_000, "scratched bumper")
    assert store.settle_claim(claim, "approve").payout_cents == 0


def test_deny_claim_and_double_settle_rejected():
    store = PolicyStore()
    policy = store.create_policy(validate_policy(_policy()))
    claim = store.file_claim(policy, 100_000, "hail damage")
    denied = store.settle_claim(claim, "deny")
    assert denied.status == "denied" and denied.payout_cents == 0
    with pytest.raises(ValidationError):
        store.settle_claim(claim, "approve")


def test_quote_cache_ttl_expiry():
    cache = QuoteCache(ttl_seconds=0.05)
    cache.put("k", 123)
    assert cache.get("k") == 123
    time.sleep(0.07)
    assert cache.get("k") is None


def test_event_publisher_offsets_and_topics():
    events = EventPublisher()
    first = events.publish("policy.created", "pol_000001", {"policy_id": "pol_000001"})
    second = events.publish("policy.created", "pol_000002", {"policy_id": "pol_000002"})
    events.publish("claim.filed", "clm_000001", {"claim_id": "clm_000001"})
    assert first["offset"] == 0 and second["offset"] == 1
    assert events.count("policy.created") == 2
    assert events.count() == 3


# --- HTTP integration ---


@pytest.fixture(scope="module")
def server():
    srv = create_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _request(server, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    payload = json.dumps(body) if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode() or "{}")
    conn.close()
    return resp.status, data


def test_policy_create_get_quote_flow(server):
    status, policy = _request(server, "POST", "/v1/policies", _policy())
    assert status == 201
    assert policy["premium_cents"] == 82_500
    assert policy["status"] == "active"
    policy_id = policy["id"]

    status, fetched = _request(server, "GET", f"/v1/policies/{policy_id}")
    assert status == 200 and fetched["id"] == policy_id

    # First quote read is served from the cache warmed at creation.
    status, quote = _request(server, "GET", f"/v1/policies/{policy_id}/quote")
    assert status == 200
    assert quote["premium_cents"] == 82_500
    assert quote["cached"] is True


def test_policy_validation_error_returns_400(server):
    status, data = _request(server, "POST", "/v1/policies", _policy(policy_type="life"))
    assert status == 400
    assert "policy_type" in data["error"]


def test_unknown_policy_returns_404(server):
    status, data = _request(server, "GET", "/v1/policies/pol_999999")
    assert status == 404
    assert data["error"] == "policy not found"


def test_claim_flow_end_to_end_with_events(server):
    _, policy = _request(server, "POST", "/v1/policies", _policy(holder_id="holder_9"))
    policy_id = policy["id"]
    before = server.events.count()

    status, claim = _request(
        server,
        "POST",
        f"/v1/policies/{policy_id}/claims",
        {"amount_cents": 200_000, "description": "rear-end collision"},
    )
    assert status == 201
    assert claim["status"] == "filed"
    claim_id = claim["id"]

    status, listing = _request(server, "GET", f"/v1/policies/{policy_id}/claims")
    assert status == 200
    assert [c["id"] for c in listing["claims"]] == [claim_id]

    status, settled = _request(
        server, "POST", f"/v1/claims/{claim_id}/settle", {"decision": "approve"}
    )
    assert status == 200
    assert settled["status"] == "settled"
    assert settled["payout_cents"] == 150_000

    status, events = _request(server, "GET", "/v1/events?topic=claim.settled")
    assert status == 200
    assert any(e["key"] == claim_id for e in events["events"])
    assert server.events.count() == before + 2  # claim.filed + claim.settled


def test_claim_over_coverage_returns_400(server):
    _, policy = _request(server, "POST", "/v1/policies", _policy(holder_id="holder_10"))
    status, data = _request(
        server,
        "POST",
        f"/v1/policies/{policy['id']}/claims",
        {"amount_cents": 99_000_00, "description": "total loss"},
    )
    assert status == 400
    assert "coverage limit" in data["error"]


def test_settle_unknown_claim_returns_404(server):
    status, data = _request(
        server, "POST", "/v1/claims/clm_999999/settle", {"decision": "approve"}
    )
    assert status == 404
    assert data["error"] == "claim not found"
