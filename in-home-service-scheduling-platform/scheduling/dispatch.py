"""Partner dispatch client: retries transient failures, fails fast
behind a circuit breaker, and degrades gracefully.

A real in-home platform confirms appointments with partner technician
networks over the network; that call can fail transiently (retry) or
the partner can be down (breaker opens, caller gets a fast, explicit
error instead of hanging). The client here is a small stand-in with
injectable behaviour so the retry/breaker paths are testable.
"""
from __future__ import annotations

from .events import EventStore, new_event
from .resilience import CircuitBreaker, CircuitOpenError, retry_call


class PartnerDispatchClient:
    """Dispatches a confirmed appointment to a partner network.

    ``send`` is the transport, injected by the caller (a real HTTP call
    in production, a stub in tests/demo). Retries use exponential
    backoff; the breaker trips after ``failure_threshold`` consecutive
    failures and the call then fails fast with CircuitOpenError.
    """

    def __init__(self, send, max_attempts: int = 3,
                 failure_threshold: int = 3, reset_timeout_s: float = 30.0):
        self._send = send
        self.breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            reset_timeout_s=reset_timeout_s)
        self.max_attempts = max_attempts

    def dispatch(self, appointment_id: str, payload: dict) -> dict:
        def attempt():
            return self._send(appointment_id, payload)

        result, attempts = retry_call(
            lambda: self.breaker.call(attempt),
            max_attempts=self.max_attempts,
            sleep=lambda s: None)  # no real waiting in the request path
        return {"appointment_id": appointment_id, "attempts": attempts,
                "partner_response": result}


def record_dispatch(store: EventStore, appointment_id: str, outcome: str,
                    attempts: int):
    """Audit-trail event for a dispatch attempt (success or failure)."""
    event = new_event(appointment_id, "DispatchAttempted",
                      store.next_version(appointment_id),
                      {"outcome": outcome, "attempts": attempts})
    store.append(event)
    return event
