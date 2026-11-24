"""Resilience patterns for the model API gateway.

The gateway sits in front of model backends that fail in ordinary ways:
a backend goes down, a deploy makes one slow, a traffic spike saturates
one. This module adds the three patterns the gateway uses to keep serving
through those failures instead of passing them straight to callers:

- Circuit breaker — stop calling a backend that keeps failing, probe it
  later, and close again only after it proves healthy.
- Retry with exponential backoff and full jitter — retry transient
  failures without hammering a recovering backend in lockstep.
- Bulkhead — cap concurrent calls per backend so one slow backend cannot
  exhaust the gateway's workers for every other model.

`ResilientRouter` ties them together around the existing `Router`: it
picks backends in router order, runs each call through that backend's
breaker and bulkhead, retries transient failures, and fails over to the
next backend. All state is in memory and all backends here are synthetic;
nothing in this module describes a real platform or real traffic.
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout


class CircuitBreaker:
    """Per-backend circuit breaker: closed -> open -> half-open -> closed.

    Closed: calls pass through; `failure_threshold` consecutive failures
    trip the breaker open. Open: calls fail fast with `CircuitOpenError`
    until `reset_timeout_s` passes. Half-open: a limited number of trial
    calls (`half_open_trials`) are allowed; one success closes the breaker,
    one failure re-opens it.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(self, name, failure_threshold=3, reset_timeout_s=30.0,
                 half_open_trials=1):
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.reset_timeout_s = float(reset_timeout_s)
        self.half_open_trials = int(half_open_trials)
        self._lock = threading.Lock()
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = None
        self._trials_left = 0
        self.trips = 0
        self.rejected = 0

    @property
    def state(self):
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self):
        if (self._state == self.OPEN and self._opened_at is not None
                and time.monotonic() - self._opened_at >= self.reset_timeout_s):
            self._state = self.HALF_OPEN
            self._trials_left = self.half_open_trials

    def allow(self):
        """True if a trial call may proceed; False if the breaker is open."""
        with self._lock:
            self._maybe_half_open()
            if self._state == self.OPEN:
                self.rejected += 1
                return False
            if self._state == self.HALF_OPEN:
                if self._trials_left <= 0:
                    self.rejected += 1
                    return False
                self._trials_left -= 1
            return True

    def record_success(self):
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
            self._failures = 0
            self._opened_at = None

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._state == self.HALF_OPEN:
                self._open()
            elif self._failures >= self.failure_threshold:
                self._open()

    def _open(self):
        self._state = self.OPEN
        self._opened_at = time.monotonic()
        self._trials_left = 0
        self.trips += 1

    def snapshot(self):
        return {
            "name": self.name,
            "state": self.state,
            "consecutive_failures": self._failures,
            "trips": self.trips,
            "rejected": self.rejected,
        }


class CircuitOpenError(Exception):
    """Raised when a call is refused because the breaker is open."""


class RetryPolicy:
    """Retry transient failures with exponential backoff and full jitter.

    Delay for attempt `n` (1-based) is a uniform draw in [0, base * 2**n],
    capped at `max_delay_s`. Jitter spreads retries so a recovering
    backend is not hit by every caller at the same instant.
    """

    def __init__(self, max_attempts=3, base_delay_s=0.1, max_delay_s=5.0,
                 retryable=(Exception,), rng=None, sleep=None):
        self.max_attempts = int(max_attempts)
        self.base_delay_s = float(base_delay_s)
        self.max_delay_s = float(max_delay_s)
        self.retryable = retryable
        self._rng = rng or random.Random()
        self._sleep = sleep or time.sleep

    def delay_for(self, attempt):
        """Backoff delay before attempt `attempt` (1-based)."""
        cap = min(self.max_delay_s, self.base_delay_s * (2 ** attempt))
        return self._rng.uniform(0, cap)

    def call(self, fn, *args, **kwargs):
        """Call `fn`, retrying retryable errors up to `max_attempts` times.

        Returns (result, attempts_used). Raises the last error when the
        attempts run out, or immediately for non-retryable errors.
        """
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn(*args, **kwargs), attempt
            except self.retryable as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                self._sleep(self.delay_for(attempt))
        raise last_error


class Bulkhead:
    """Cap concurrent calls so one slow backend cannot starve the rest.

    A bounded semaphore per backend: `acquire()` returns False (instead of
    blocking) when the cap is reached, so the gateway can fail over or
    shed load immediately rather than queueing behind a stuck backend.
    """

    def __init__(self, name, max_concurrent=10):
        self.name = name
        self.max_concurrent = int(max_concurrent)
        self._semaphore = threading.Semaphore(self.max_concurrent)
        self.rejected = 0
        self._lock = threading.Lock()

    def acquire(self):
        ok = self._semaphore.acquire(blocking=False)
        if not ok:
            with self._lock:
                self.rejected += 1
        return ok

    def release(self):
        self._semaphore.release()

    def snapshot(self):
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "rejected": self.rejected,
        }


def call_with_timeout(fn, timeout_s, *args, **kwargs):
    """Run `fn` and raise TimeoutError if it does not finish in time."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout:
            raise TimeoutError(
                "call did not finish within %.3fs" % timeout_s)


class ResilientRouter:
    """Router + per-backend breaker, bulkhead, retry and timeout.

    `invoke(model, fn, ...)` picks backends in router order and runs `fn`
    (called with the chosen backend as its first argument) through that
    backend's circuit breaker and bulkhead, retrying transient failures.
    A backend whose breaker is open or whose bulkhead is full is skipped
    and the next backend is tried. Returns (backend_id, result, attempts).
    Raises `RuntimeError` when no backend could serve the call.
    """

    def __init__(self, router, failure_threshold=3, reset_timeout_s=30.0,
                 max_concurrent=10, retry=None, timeout_s=None):
        self.router = router
        self.retry = retry or RetryPolicy(max_attempts=2)
        self.timeout_s = timeout_s
        self._breakers = {}
        self._bulkheads = {}
        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s
        self._max_concurrent = max_concurrent

    def _per_backend(self, backend_id):
        if backend_id not in self._breakers:
            self._breakers[backend_id] = CircuitBreaker(
                backend_id, self._failure_threshold, self._reset_timeout_s)
            self._bulkheads[backend_id] = Bulkhead(
                backend_id, self._max_concurrent)
        return self._breakers[backend_id], self._bulkheads[backend_id]

    def invoke(self, model, fn, *args, **kwargs):
        backends = self.router.registry.backends_for(model)
        if not backends:
            raise RuntimeError("no backends registered for model %r" % model)
        failures = []
        for backend in backends:
            breaker, bulkhead = self._per_backend(backend.backend_id)
            if not breaker.allow():
                failures.append((backend.backend_id, "circuit open"))
                continue
            if not bulkhead.acquire():
                failures.append((backend.backend_id, "bulkhead full"))
                continue
            try:
                def guarded():
                    if self.timeout_s is not None:
                        return call_with_timeout(
                            fn, self.timeout_s, backend, *args, **kwargs)
                    return fn(backend, *args, **kwargs)

                result, attempts = self.retry.call(guarded)
                breaker.record_success()
                return backend.backend_id, result, attempts
            except Exception as exc:  # noqa: BLE001 - recorded, then failover
                breaker.record_failure()
                failures.append((backend.backend_id, str(exc)))
            finally:
                bulkhead.release()
        raise RuntimeError(
            "all backends failed for model %r: %s" % (model, failures))

    def snapshot(self, model):
        out = {}
        for backend in self.router.registry.backends_for(model):
            breaker, bulkhead = self._per_backend(backend.backend_id)
            out[backend.backend_id] = {
                "breaker": breaker.snapshot(),
                "bulkhead": bulkhead.snapshot(),
            }
        return out
