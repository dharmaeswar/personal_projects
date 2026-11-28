"""Tests: verifiable intent and delegated tokens."""

from datetime import datetime, timedelta, timezone

import pytest

from agentic_checkout.intent import (
    AgentIntent, Delegation, intent_fingerprint, validate_intent,
)
from agentic_checkout.tokens import (
    ReplayGuard, TokenError, issue_token, verify_token,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
SECRET = b"test-secret"


def _delegation(**overrides):
    base = dict(
        user_id="user_001", agent_id="agent_01",
        allowed_actions=frozenset({"checkout.create", "payment.authorize"}),
        merchant_allowlist=frozenset({"merchant_a"}),
        max_amount_cents=10_000, allowed_currencies=frozenset({"USD"}),
        expires_at=NOW + timedelta(days=1),
    )
    base.update(overrides)
    return Delegation(**base)


def _intent(**overrides):
    base = dict(
        agent_id="agent_01", user_id="user_001", merchant_id="merchant_a",
        action="checkout.create", amount_cents=5000, currency="USD",
        idempotency_key="key-1",
    )
    base.update(overrides)
    return AgentIntent(**base)


def test_valid_intent_has_no_violations():
    assert validate_intent(_intent(), _delegation(), NOW) == []


def test_intent_over_cap_is_rejected():
    problems = validate_intent(_intent(amount_cents=10_001), _delegation(), NOW)
    assert any("cap" in p for p in problems)


def test_intent_wrong_action_merchant_currency():
    problems = validate_intent(
        _intent(action="payment.refund", merchant_id="merchant_b", currency="EUR"),
        _delegation(), NOW)
    assert len(problems) == 3


def test_expired_delegation_is_rejected():
    problems = validate_intent(_intent(), _delegation(expires_at=NOW), NOW)
    assert any("expired" in p for p in problems)


def test_fingerprint_is_stable_and_differs_by_amount():
    a = intent_fingerprint(_intent())
    assert a == intent_fingerprint(_intent())
    assert a != intent_fingerprint(_intent(amount_cents=5001))


def test_token_round_trip():
    token = issue_token(agent_id="agent_01", user_id="user_001",
                        scopes=["checkout.create"], merchant_allowlist=["merchant_a"],
                        max_amount_cents=10_000, expires_at=NOW + timedelta(hours=1),
                        secret=SECRET, token_id="tok_test_1")
    decoded = verify_token(token, SECRET, NOW)
    assert decoded.token_id == "tok_test_1"
    assert decoded.allows("checkout.create", "merchant_a", 5000, NOW) == []


def test_tampered_token_fails_signature():
    token = issue_token(agent_id="agent_01", user_id="user_001",
                        scopes=["checkout.create"], max_amount_cents=10_000,
                        expires_at=NOW + timedelta(hours=1), secret=SECRET)
    body, _sig = token.rsplit(".", 1)
    tampered = body[:-2] + "AA" + "." + token.rsplit(".", 1)[1]
    with pytest.raises(TokenError):
        verify_token(tampered, SECRET, NOW)


def test_expired_token_is_rejected():
    token = issue_token(agent_id="agent_01", user_id="user_001",
                        scopes=["checkout.create"], max_amount_cents=10_000,
                        expires_at=NOW, secret=SECRET)
    with pytest.raises(TokenError, match="expired"):
        verify_token(token, SECRET, NOW)


def test_token_scope_and_cap_enforced():
    token = issue_token(agent_id="agent_01", user_id="user_001",
                        scopes=["checkout.create"], max_amount_cents=1000,
                        expires_at=NOW + timedelta(hours=1), secret=SECRET)
    decoded = verify_token(token, SECRET, NOW)
    assert decoded.allows("payment.refund", "merchant_a", 500, NOW)
    assert decoded.allows("checkout.create", "merchant_a", 1001, NOW)


def test_replay_guard_blocks_second_use():
    guard = ReplayGuard()
    assert guard.check_and_mark("tok_1", "key-1") is True
    assert guard.check_and_mark("tok_1", "key-1") is False
    assert guard.check_and_mark("tok_1", "key-2") is True
