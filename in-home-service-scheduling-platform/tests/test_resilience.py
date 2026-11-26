import pytest

from scheduling.dispatch import PartnerDispatchClient
from scheduling.resilience import CircuitBreaker, CircuitOpenError, retry_call


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("partner timeout")
        return {"dispatched": True}

    result, attempts = retry_call(flaky, max_attempts=3, sleep=lambda s: None)
    assert result == {"dispatched": True} and attempts == 3


def test_retry_gives_up_after_max_attempts():
    with pytest.raises(ConnectionError):
        retry_call(lambda: (_ for _ in ()).throw(ConnectionError("down")),
                   max_attempts=2, sleep=lambda s: None)


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_s=60)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "never reached")


def test_circuit_breaker_recovers_after_cooldown():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=0)
    with pytest.raises(ConnectionError):
        breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert breaker.state == "half-open"
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == "closed"


def test_dispatch_client_retries_then_succeeds():
    calls = {"n": 0}

    def send(appt_id, payload):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("partner timeout")
        return {"confirmation": "P-123"}

    client = PartnerDispatchClient(send)
    result = client.dispatch("appt-1", {"technician_id": "tech-1"})
    assert result["attempts"] == 3
    assert result["partner_response"] == {"confirmation": "P-123"}


def test_dispatch_client_fails_fast_when_breaker_open():
    def send(appt_id, payload):
        raise ConnectionError("partner down")

    client = PartnerDispatchClient(send, max_attempts=1, failure_threshold=1)
    with pytest.raises(ConnectionError):
        client.dispatch("appt-1", {})
    # Breaker is now open: the next call fails fast without calling send.
    with pytest.raises(CircuitOpenError):
        client.dispatch("appt-1", {})
