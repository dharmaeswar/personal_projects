"""Demo: the gateway serving through a failing backend.

A model has two backends. The fast one fails for a while (a bad deploy),
then recovers. The demo shows, in order:

1. Retries absorb a transient failure on the fast backend.
2. Repeated failures trip the fast backend's circuit breaker, so the
   gateway fails over to the slow backend instead of waiting on a dead one.
3. After the reset timeout, a half-open probe succeeds and the breaker
   closes — traffic returns to the fast backend.
4. A bulkhead cap sheds load instead of queueing behind a stuck backend.

All backends, failures and timings are synthetic and local. Run with:
    python run_resilience_demo.py
"""

import time

from gateway.resilience import (
    CircuitBreaker,
    ResilientRouter,
    RetryPolicy,
)
from gateway.router import Backend, ModelRegistry, Router


def _flaky_backend(name, fail_for_calls):
    """A fake backend call that fails the first `fail_for_calls` times."""
    state = {"calls": 0}

    def call(backend):
        state["calls"] += 1
        if backend.backend_id == name and state["calls"] <= fail_for_calls:
            raise RuntimeError("%s is failing (call %d)" % (name, state["calls"]))
        return "served by %s (call %d)" % (backend.backend_id, state["calls"])

    return call


def main():
    registry = ModelRegistry()
    registry.register(Backend("fast", "llama-4-scout", 100.0, 10))
    registry.register(Backend("slow", "llama-4-scout", 300.0, 10))
    resilient = ResilientRouter(
        Router(registry),
        failure_threshold=2,
        reset_timeout_s=0.2,
        max_concurrent=1,
        retry=RetryPolicy(max_attempts=3, base_delay_s=0.01,
                          sleep=lambda s: None),
    )

    print("== 1. Transient failure: retry absorbs it ==")
    call = _flaky_backend("fast", fail_for_calls=1)
    backend_id, result, attempts = resilient.invoke("llama-4-scout", call)
    print("  %s in %d attempt(s): %s" % (backend_id, attempts, result))

    print("== 2. Repeated failure: breaker trips, traffic fails over ==")
    call = _flaky_backend("fast", fail_for_calls=99)
    for i in range(2):
        backend_id, result, attempts = resilient.invoke("llama-4-scout", call)
        print("  call %d -> %s: %s" % (i + 1, backend_id, result))
    snapshot = resilient.snapshot("llama-4-scout")
    print("  fast breaker state: %s (trips: %d)"
          % (snapshot["fast"]["breaker"]["state"],
             snapshot["fast"]["breaker"]["trips"]))

    print("== 3. Recovery: half-open probe closes the breaker ==")
    time.sleep(0.25)  # past the 0.2s reset timeout
    call = _flaky_backend("fast", fail_for_calls=0)
    backend_id, result, attempts = resilient.invoke("llama-4-scout", call)
    print("  %s in %d attempt(s): %s" % (backend_id, attempts, result))
    snapshot = resilient.snapshot("llama-4-scout")
    print("  fast breaker state: %s" % snapshot["fast"]["breaker"]["state"])

    print("== 4. Bulkhead: a full backend is skipped, not queued behind ==")
    _, bulkhead = resilient._per_backend("fast")
    assert bulkhead.acquire() is True  # hold fast's only slot (cap is 1)
    backend_id, result, _ = resilient.invoke(
        "llama-4-scout", lambda b: "served by " + b.backend_id)
    print("  fast full -> %s: %s" % (backend_id, result))
    bulkhead.release()

    print("Demo complete: gateway kept serving through every failure.")


if __name__ == "__main__":
    main()
