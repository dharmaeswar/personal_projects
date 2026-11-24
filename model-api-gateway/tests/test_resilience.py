"""Tests for gateway/resilience.py — breaker, retry, bulkhead, timeout."""

import time

import pytest

from gateway.resilience import (
    Bulkhead,
    CircuitBreaker,
    ResilientRouter,
    RetryPolicy,
    call_with_timeout,
)
from gateway.router import Backend, ModelRegistry, Router


# --- Circuit breaker ---

def test_breaker_stays_closed_under_threshold():
    breaker = CircuitBreaker("b1", failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.CLOSED
    assert breaker.allow() is True


def test_breaker_opens_at_threshold_and_rejects():
    breaker = CircuitBreaker("b1", failure_threshold=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN
    assert breaker.allow() is False
    assert breaker.snapshot()["rejected"] == 1


def test_breaker_success_resets_failure_count():
    breaker = CircuitBreaker("b1", failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.CLOSED


def test_breaker_half_open_probe_success_closes():
    breaker = CircuitBreaker("b1", failure_threshold=1, reset_timeout_s=0.01)
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN
    time.sleep(0.02)
    assert breaker.state == CircuitBreaker.HALF_OPEN
    assert breaker.allow() is True
    breaker.record_success()
    assert breaker.state == CircuitBreaker.CLOSED


def test_breaker_half_open_probe_failure_reopens():
    breaker = CircuitBreaker("b1", failure_threshold=1, reset_timeout_s=0.01,
                             half_open_trials=1)
    breaker.record_failure()
    time.sleep(0.02)
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN
    assert breaker.snapshot()["trips"] == 2


def test_breaker_half_open_trial_limit():
    breaker = CircuitBreaker("b1", failure_threshold=1, reset_timeout_s=0.01,
                             half_open_trials=1)
    breaker.record_failure()
    time.sleep(0.02)
    assert breaker.allow() is True   # the one trial
    assert breaker.allow() is False  # no trials left


# --- Retry ---

def test_retry_succeeds_on_second_attempt():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    policy = RetryPolicy(max_attempts=3, sleep=lambda s: None)
    result, attempts = policy.call(flaky)
    assert (result, attempts) == ("ok", 2)


def test_retry_raises_after_attempts_exhausted():
    policy = RetryPolicy(max_attempts=2, sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        policy.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_retry_does_not_retry_non_retryable():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("not retryable")

    policy = RetryPolicy(max_attempts=3, retryable=(RuntimeError,),
                         sleep=lambda s: None)
    with pytest.raises(ValueError):
        policy.call(fn)
    assert calls["n"] == 1


def test_backoff_delay_capped_and_bounded():
    policy = RetryPolicy(base_delay_s=1.0, max_delay_s=2.0)
    for attempt in range(1, 6):
        delay = policy.delay_for(attempt)
        assert 0 <= delay <= 2.0
    assert policy.delay_for(1) <= 2.0  # cap 1.0 * 2 = 2.0


# --- Bulkhead ---

def test_bulkhead_rejects_over_capacity():
    bulkhead = Bulkhead("b1", max_concurrent=1)
    assert bulkhead.acquire() is True
    assert bulkhead.acquire() is False
    assert bulkhead.snapshot()["rejected"] == 1
    bulkhead.release()
    assert bulkhead.acquire() is True
    bulkhead.release()


# --- Timeout ---

def test_call_with_timeout_raises_on_slow_call():
    with pytest.raises(TimeoutError):
        call_with_timeout(lambda: time.sleep(0.5), 0.05)


def test_call_with_timeout_returns_fast_result():
    assert call_with_timeout(lambda: 42, 1.0) == 42


# --- ResilientRouter ---

def _registry():
    registry = ModelRegistry()
    registry.register(Backend("fast", "llama-4-scout", 100.0, 10))
    registry.register(Backend("slow", "llama-4-scout", 300.0, 10))
    return registry


def test_resilient_router_serves_first_healthy_backend():
    resilient = ResilientRouter(Router(_registry()))
    backend_id, result, attempts = resilient.invoke(
        "llama-4-scout", lambda b: "served by " + b.backend_id)
    assert backend_id == "fast"
    assert result == "served by fast"
    assert attempts == 1


def test_resilient_router_fails_over_when_backend_errors():
    resilient = ResilientRouter(Router(_registry()))

    def fn(backend):
        if backend.backend_id == "fast":
            raise RuntimeError("fast is down")
        return "served by slow"

    backend_id, result, attempts = resilient.invoke("llama-4-scout", fn)
    assert backend_id == "slow"
    assert result == "served by slow"


def test_resilient_router_retries_transient_failure_on_same_backend():
    resilient = ResilientRouter(
        Router(_registry()),
        retry=RetryPolicy(max_attempts=3, sleep=lambda s: None))
    calls = {"n": 0}

    def fn(backend):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    backend_id, result, attempts = resilient.invoke("llama-4-scout", fn)
    assert (backend_id, result, attempts) == ("fast", "ok", 2)


def test_resilient_router_skips_open_breaker():
    resilient = ResilientRouter(Router(_registry()), failure_threshold=1,
                                reset_timeout_s=60.0)

    def fail_fast_only(backend):
        if backend.backend_id == "fast":
            raise RuntimeError("down")
        return "served by slow"

    # First call: fast trips its breaker, slow serves.
    backend_id, _, _ = resilient.invoke("llama-4-scout", fail_fast_only)
    assert backend_id == "slow"
    # Second call: fast is skipped (breaker open), slow serves again.
    backend_id, _, _ = resilient.invoke("llama-4-scout", fail_fast_only)
    assert backend_id == "slow"
    snapshot = resilient.snapshot("llama-4-scout")
    assert snapshot["fast"]["breaker"]["state"] == CircuitBreaker.OPEN


def test_resilient_router_raises_when_all_backends_fail():
    resilient = ResilientRouter(Router(_registry()))
    with pytest.raises(RuntimeError, match="all backends failed"):
        resilient.invoke("llama-4-scout",
                         lambda b: (_ for _ in ()).throw(RuntimeError("down")))


def test_resilient_router_unknown_model():
    resilient = ResilientRouter(Router(_registry()))
    with pytest.raises(RuntimeError, match="no backends registered"):
        resilient.invoke("no-such-model", lambda b: "ok")


def test_resilient_router_timeout_counts_as_failure_and_fails_over():
    resilient = ResilientRouter(Router(_registry()), timeout_s=0.05)

    def fn(backend):
        if backend.backend_id == "fast":
            time.sleep(0.3)
        return "served by " + backend.backend_id

    backend_id, result, _ = resilient.invoke("llama-4-scout", fn)
    assert backend_id == "slow"
    assert result == "served by slow"


def test_bulkhead_full_backend_is_skipped():
    registry = _registry()
    resilient = ResilientRouter(Router(registry), max_concurrent=1)
    _, bulkhead = resilient._per_backend("fast")
    assert bulkhead.acquire() is True  # hold fast's only slot

    # fast is full, so the call must go to slow even though fast is first.
    backend_id, result, _ = resilient.invoke(
        "llama-4-scout", lambda b: "served by " + b.backend_id)
    assert backend_id == "slow"
    assert result == "served by slow"
    bulkhead.release()
