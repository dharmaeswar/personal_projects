"""Token-bucket rate limiting, per API key.

Each key gets two budgets: requests per minute and tokens per minute.
Buckets refill continuously at the configured rate. A request is allowed
only when both budgets can pay for it.
"""

import threading
import time

# Default budgets per tier: (requests_per_minute, tokens_per_minute).
TIER_BUDGETS = {
    "free": (60, 20_000),
    "pro": (600, 200_000),
    "scale": (6_000, 2_000_000),
}


class TokenBucket:
    def __init__(self, capacity, refill_per_second, now=None):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self.updated_at = time.time() if now is None else now
        self._lock = threading.Lock()

    def _refill(self, now):
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now

    def try_consume(self, amount, now=None):
        """Consume `amount` tokens if available. Returns True when allowed."""
        now = time.time() if now is None else now
        with self._lock:
            self._refill(now)
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def retry_after_seconds(self, amount, now=None):
        """Seconds until `amount` tokens are available (0 if available now)."""
        now = time.time() if now is None else now
        with self._lock:
            self._refill(now)
            if self.tokens >= amount:
                return 0.0
            deficit = amount - self.tokens
            return deficit / self.refill_per_second if self.refill_per_second else float("inf")


class RateLimiter:
    """One request-bucket and one token-bucket per API key."""

    def __init__(self, budgets=None):
        self.budgets = budgets or TIER_BUDGETS
        self._buckets = {}  # (key_id, kind) -> TokenBucket
        self._lock = threading.Lock()

    def _bucket(self, key_id, kind, capacity, now):
        with self._lock:
            bucket = self._buckets.get((key_id, kind))
            if bucket is None:
                bucket = TokenBucket(capacity, capacity / 60.0, now=now)
                self._buckets[(key_id, kind)] = bucket
            return bucket

    def check(self, api_key, prompt_tokens, now=None):
        """Return (allowed, retry_after_seconds) for one request.

        Consumes 1 request and `prompt_tokens` tokens only when allowed;
        a rejected request consumes nothing.
        """
        now = time.time() if now is None else now
        req_per_min, tok_per_min = self.budgets[api_key.tier]
        req_bucket = self._bucket(api_key.key_id, "req", req_per_min, now)
        tok_bucket = self._bucket(api_key.key_id, "tok", tok_per_min, now)
        # Peek first so a rejection does not partially consume a budget.
        req_wait = req_bucket.retry_after_seconds(1, now=now)
        tok_wait = tok_bucket.retry_after_seconds(prompt_tokens, now=now)
        wait = max(req_wait, tok_wait)
        if wait > 0:
            return False, wait
        req_bucket.try_consume(1, now=now)
        tok_bucket.try_consume(prompt_tokens, now=now)
        return True, 0.0
