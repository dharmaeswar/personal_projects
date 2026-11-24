import pytest

from capplanner.entitlement import Quota, QuotaLedger, TokenBucket


def test_token_bucket_admits_within_burst():
    bucket = TokenBucket(rate=10.0, burst=5.0, now=0.0)
    assert all(bucket.admit(now=0.0) for _ in range(5))
    assert not bucket.admit(now=0.0)


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(rate=10.0, burst=5.0, now=0.0)
    for _ in range(5):
        assert bucket.admit(now=0.0)
    assert not bucket.admit(now=0.0)
    assert bucket.admit(now=0.5)  # 5 tokens refilled by t=0.5


def test_token_bucket_rejects_bad_params():
    with pytest.raises(ValueError):
        TokenBucket(rate=0, burst=5.0)
    with pytest.raises(ValueError):
        TokenBucket(rate=10.0, burst=0)


def test_ledger_throttles_unknown_customer():
    ledger = QuotaLedger()
    status, reason = ledger.admit_request("ghost")
    assert status == "throttled"
    assert reason == "unknown customer"


def test_ledger_throttles_over_rate():
    ledger = QuotaLedger()
    ledger.set_quota(Quota("a", max_rps=10.0, max_storage_gb=50.0))
    # Burst of 10 tokens at t=0, then 150 rps worth of requests at fixed time.
    admitted = sum(
        1 for _ in range(50)
        if ledger.admit_request("a", now=0.0)[0] == "admitted"
    )
    assert admitted == 10


def test_ledger_throttles_over_storage():
    ledger = QuotaLedger()
    ledger.set_quota(Quota("a", max_rps=100.0, max_storage_gb=10.0))
    ledger.record_storage("a", 12.0)
    status, reason = ledger.admit_request("a")
    assert status == "throttled"
    assert reason == "storage quota exceeded"
    assert ledger.over_quota_customers() == ["a"]


def test_limit_increase_needs_headroom():
    ledger = QuotaLedger()
    ledger.set_quota(Quota("a", max_rps=100.0, max_storage_gb=50.0))
    approved, _ = ledger.request_limit_increase("a", 200.0, fleet_free_rps=50.0)
    assert not approved
    approved, reason = ledger.request_limit_increase("a", 200.0, fleet_free_rps=500.0)
    assert approved
    assert ledger.quotas["a"].max_rps == 200.0


def test_limit_increase_rejects_non_increase():
    ledger = QuotaLedger()
    ledger.set_quota(Quota("a", max_rps=100.0, max_storage_gb=50.0))
    approved, reason = ledger.request_limit_increase("a", 100.0, fleet_free_rps=500.0)
    assert not approved
    assert "not an increase" in reason
