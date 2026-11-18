"""Unit tests: installment math, validation, payments, idempotency, retry."""

import pytest

from payments_api.idempotency import IdempotencyStore, SimulatedLedger, retry_with_backoff
from payments_api.models import (
    Loan,
    ValidationError,
    build_schedule,
    monthly_payment_cents,
    validate_checkout,
)


def _payload(**overrides):
    base = {
        "principal_cents": 120_000,  # $1,200
        "apr_bps": 1500,  # 15%
        "term_months": 12,
        "merchant_id": "merchant_1",
        "customer_id": "cust_42",
    }
    base.update(overrides)
    return base


# --- installment math -------------------------------------------------

def test_zero_apr_splits_principal_evenly():
    assert monthly_payment_cents(120_000, 0, 12) == 10_000


def test_known_payment_1200_at_15pct_12mo():
    # $1,200 at 15% APR over 12 months: ~$108.31/mo -> 10,831 cents.
    assert monthly_payment_cents(120_000, 1500, 12) == 10_831


def test_schedule_sums_to_principal_plus_interest():
    schedule = build_schedule(120_000, 1500, 12)
    assert len(schedule) == 12
    assert sum(s["principal_cents"] for s in schedule) == 120_000
    assert sum(s["installment_cents"] for s in schedule) == 129_972
    assert schedule[-1]["remaining_balance_cents"] == 0
    assert schedule[0]["interest_cents"] == 1_500  # 120,000 * 15% / 12


def test_schedule_zero_apr_is_flat():
    schedule = build_schedule(90_000, 0, 3)
    assert [s["installment_cents"] for s in schedule] == [30_000, 30_000, 30_000]
    assert all(s["interest_cents"] == 0 for s in schedule)


# --- validation --------------------------------------------------------

def test_valid_payload_passes_through():
    assert validate_checkout(_payload()) == _payload()


@pytest.mark.parametrize(
    "override",
    [
        {"principal_cents": 0},
        {"principal_cents": 99},
        {"principal_cents": 10_000_001},
        {"principal_cents": 1200.5},
        {"apr_bps": -1},
        {"apr_bps": 3601},
        {"term_months": 2},
        {"term_months": 61},
        {"merchant_id": ""},
        {"customer_id": "bad id!"},
    ],
)
def test_invalid_payloads_rejected(override):
    with pytest.raises(ValidationError):
        validate_checkout(_payload(**override))


def test_non_object_body_rejected():
    with pytest.raises(ValidationError):
        validate_checkout(["not", "a", "dict"])


# --- payments -----------------------------------------------------------

def _loan():
    return Loan(
        id="loan_000001",
        principal_cents=120_000,
        apr_bps=1500,
        term_months=12,
        merchant_id="merchant_1",
        customer_id="cust_42",
        schedule=build_schedule(120_000, 1500, 12),
    )


def test_payment_reduces_balance_and_marks_paid_off():
    loan = _loan()
    total = sum(s["installment_cents"] for s in loan.schedule)
    first = loan.schedule[0]["installment_cents"]
    loan.apply_payment(first)
    assert loan.paid_cents == first
    assert loan.status == "active"
    loan.apply_payment(total - first)
    assert loan.status == "paid_off"
    assert loan.paid_cents == total


def test_overpayment_rejected():
    loan = _loan()
    total = sum(s["installment_cents"] for s in loan.schedule)
    with pytest.raises(ValidationError):
        loan.apply_payment(total + 1)


def test_payment_on_paid_off_loan_rejected():
    loan = _loan()
    total = sum(s["installment_cents"] for s in loan.schedule)
    loan.apply_payment(total)
    with pytest.raises(ValidationError):
        loan.apply_payment(100)


def test_non_positive_payment_rejected():
    with pytest.raises(ValidationError):
        _loan().apply_payment(0)


# --- idempotency + retry -------------------------------------------------

def test_idempotency_store_returns_copy_and_counts_keys():
    store = IdempotencyStore()
    store.put("key-1", {"id": "loan_000001"})
    assert store.get("key-1") == {"id": "loan_000001"}
    assert store.get("missing") is None
    assert len(store) == 1


def test_retry_succeeds_after_transient_failures():
    ledger = SimulatedLedger(fail_times=2)
    result = retry_with_backoff(lambda: ledger.record_loan("loan_000001"), sleep=lambda s: None)
    assert result == {"loan_id": "loan_000001", "ledger_status": "recorded"}
    assert ledger.calls == 3


def test_retry_gives_up_after_max_attempts():
    ledger = SimulatedLedger(fail_times=5)
    with pytest.raises(RuntimeError):
        retry_with_backoff(lambda: ledger.record_loan("loan_000001"), sleep=lambda s: None)
    assert ledger.calls == 3


def test_retry_does_not_retry_non_transient_errors():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        retry_with_backoff(boom, sleep=lambda s: None)
    assert calls["n"] == 1
