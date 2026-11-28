"""Experiments and reliability tests."""

import pytest

from taskfeed.experiments import assign_variant, readout, two_proportion_ztest
from taskfeed.reliability import CircuitBreaker, retry_with_backoff


def test_assignment_is_deterministic_and_split():
    a = assign_variant("user-1", "ranking-v2")
    assert assign_variant("user-1", "ranking-v2") == a
    assert assign_variant("user-2", "ranking-v2") in ("control", "treatment")
    variants = {assign_variant(f"u{i}", "ranking-v2") for i in range(200)}
    assert variants == {"control", "treatment"}
    treated = sum(assign_variant(f"u{i}", "ranking-v2") == "treatment" for i in range(200))
    assert 70 <= treated <= 130  # roughly even split


def test_ztest_clear_lift_is_significant():
    z, p = two_proportion_ztest(400, 1000, 500, 1000)
    assert z > 4 and p < 0.001


def test_ztest_no_difference():
    z, p = two_proportion_ztest(500, 1000, 500, 1000)
    assert z == 0.0 and p == 1.0


def test_ztest_needs_observations():
    with pytest.raises(ValueError):
        two_proportion_ztest(0, 0, 1, 10)


def test_readout_significant_lift():
    r = readout("ranking-v2", control_success=400, control_n=1000,
                treatment_success=500, treatment_n=1000)
    assert r.significant and not r.srm_flagged
    assert r.lift == 10.0 and "Significant" in r.note


def test_readout_srm_flagged_blocks_significance():
    # 900/100 observed vs 50/50 intended: SRM fires, lift must not be trusted.
    r = readout("ranking-v2", control_success=90, control_n=100,
                treatment_success=800, treatment_n=900)
    assert r.srm_flagged and not r.significant
    assert "SRM flagged" in r.note


def test_readout_empty_raises():
    with pytest.raises(ValueError):
        readout("x", control_success=0, control_n=0, treatment_success=0, treatment_n=0)


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    value, attempts = retry_with_backoff(flaky, max_attempts=3, sleep=lambda s: None)
    assert value == "ok" and attempts == 3


def test_retry_exhausts_and_raises():
    with pytest.raises(RuntimeError):
        retry_with_backoff(lambda: (_ for _ in ()).throw(RuntimeError("down")),
                           max_attempts=2, sleep=lambda s: None)


def test_circuit_breaker_opens_and_recovers():
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=10.0)
    assert cb.allow(0.0)
    cb.record_failure(0.0)
    assert cb.allow(1.0)
    cb.record_failure(1.0)
    assert cb.is_open and not cb.allow(2.0)
    assert cb.allow(11.0)  # half-open probe allowed after cooldown
    assert not cb.allow(11.5)  # second call blocked while probe in flight
    cb.record_success()
    assert not cb.is_open and cb.allow(12.0)
