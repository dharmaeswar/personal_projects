"""Tests: token vault (Luhn, brand, masked lookup) and risk scoring."""

from datetime import datetime, timedelta, timezone

import pytest

from agentic_checkout.risk import Attempt, RiskEngine
from agentic_checkout.vault import TokenVault, VaultError

SECRET = b"vault-test-secret"
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def test_tokenize_returns_masked_record_only():
    vault = TokenVault(SECRET)
    record = vault.tokenize("4242424242424242")
    assert record.token.startswith("tok_")
    assert record.brand == "visa"
    assert record.last4 == "4242"
    assert "4242424242424242" not in record.token


def test_same_card_same_token_deterministic():
    vault = TokenVault(SECRET)
    assert vault.tokenize("4242424242424242").token == vault.tokenize("4242424242424242").token


def test_invalid_card_rejected():
    vault = TokenVault(SECRET)
    with pytest.raises(VaultError):
        vault.tokenize("4242424242424241")  # fails Luhn
    with pytest.raises(VaultError):
        vault.tokenize("123")


def test_lookup_returns_masked_record_and_unknown_fails():
    vault = TokenVault(SECRET)
    record = vault.tokenize("5555555555554444")
    assert record.brand == "mastercard"
    assert vault.lookup(record.token).last4 == "4444"
    with pytest.raises(VaultError):
        vault.lookup("tok_doesnotexist")


def test_normal_amount_is_allow():
    engine = RiskEngine(merchant_median_cents={"m1": 2500})
    decision = engine.score(Attempt("a1", "m1", 2500, "USD", NOW))
    assert decision.decision == "ALLOW"
    assert decision.score == 0


def test_amount_anomaly_scores_high():
    engine = RiskEngine(merchant_median_cents={"m1": 2500})
    decision = engine.score(Attempt("a1", "m1", 2500 * 4, "USD", NOW))
    assert decision.score >= 40
    assert decision.decision in ("REVIEW", "DENY")
    assert any("3x" in r for r in decision.reasons)


def test_velocity_triggers_review_or_deny():
    engine = RiskEngine(merchant_median_cents={"m1": 2500}, velocity_limit=3)
    for _ in range(3):
        engine.score(Attempt("a1", "m1", 100, "USD", NOW))
    decision = engine.score(Attempt("a1", "m1", 100, "USD", NOW))
    assert any("velocity" in r for r in decision.reasons)
    assert decision.decision in ("REVIEW", "DENY")


def test_blocked_merchant_is_hard_deny():
    engine = RiskEngine(merchant_median_cents={},
                        blocked_merchants=frozenset({"m_bad"}))
    decision = engine.score(Attempt("a1", "m_bad", 100, "USD", NOW))
    assert decision.decision == "DENY"
    assert decision.score == 100


def test_first_payment_to_new_merchant_adds_signal():
    engine = RiskEngine(merchant_median_cents={"m1": 2500, "m2": 2500})
    engine.score(Attempt("a1", "m1", 100, "USD", NOW))
    decision = engine.score(Attempt("a1", "m2", 100, "USD", NOW))
    assert any("first payment" in r for r in decision.reasons)
