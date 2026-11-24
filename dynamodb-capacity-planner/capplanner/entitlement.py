"""Quota and customer-entitlement enforcement.

A per-customer quota ledger with a token-bucket admission check: each
customer gets a max sustained request rate and a storage quota, and every
request is admitted or throttled against them. Limit-increase requests are
approved only when the fleet has headroom for them, so one customer cannot
starve the rest of the fleet.
"""

import time


class Quota:
    """One customer's entitlement: max sustained RPS and max stored GB."""

    def __init__(self, customer, max_rps, max_storage_gb):
        if max_rps <= 0 or max_storage_gb <= 0:
            raise ValueError("quota values must be positive")
        self.customer = customer
        self.max_rps = float(max_rps)
        self.max_storage_gb = float(max_storage_gb)

    def __repr__(self):
        return (f"Quota({self.customer!r}, max_rps={self.max_rps}, "
                f"max_storage_gb={self.max_storage_gb})")


class TokenBucket:
    """Token bucket for one customer: refills at ``rate`` tokens/sec."""

    def __init__(self, rate, burst, now=None):
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate = float(rate)
        self.burst = float(burst)
        self.tokens = float(burst)
        self.last = time.monotonic() if now is None else now

    def admit(self, tokens=1.0, now=None):
        """True if ``tokens`` are available now; consumes them on success."""
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.last)
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class QuotaLedger:
    """Holds quotas and live usage for many customers."""

    def __init__(self):
        self.quotas = {}
        self.buckets = {}
        self.usage_gb = {}

    def set_quota(self, quota):
        self.quotas[quota.customer] = quota
        self.buckets[quota.customer] = TokenBucket(
            rate=quota.max_rps, burst=quota.max_rps)
        self.usage_gb.setdefault(quota.customer, 0.0)

    def record_storage(self, customer, gb):
        if customer not in self.quotas:
            raise KeyError(f"no quota for {customer!r}")
        if gb < 0:
            raise ValueError("storage cannot be negative")
        self.usage_gb[customer] = gb

    def admit_request(self, customer, tokens=1.0, now=None):
        """Admit or throttle one request.

        Returns ("admitted", None) or ("throttled", reason).
        """
        if customer not in self.quotas:
            return "throttled", "unknown customer"
        quota = self.quotas[customer]
        if self.usage_gb.get(customer, 0.0) > quota.max_storage_gb:
            return "throttled", "storage quota exceeded"
        if self.buckets[customer].admit(tokens, now=now):
            return "admitted", None
        return "throttled", "rate quota exceeded"

    def request_limit_increase(self, customer, new_max_rps, fleet_free_rps):
        """Evaluate a limit-increase request against fleet headroom.

        Approved only when the fleet has free capacity for the increase and
        the new limit is a real increase. Returns (approved, reason).
        """
        if customer not in self.quotas:
            return False, "unknown customer"
        quota = self.quotas[customer]
        if new_max_rps <= quota.max_rps:
            return False, "requested limit is not an increase"
        increase = new_max_rps - quota.max_rps
        if increase > fleet_free_rps:
            return False, "fleet has no headroom for this increase"
        quota.max_rps = float(new_max_rps)
        self.buckets[customer] = TokenBucket(rate=new_max_rps, burst=new_max_rps)
        return True, "approved"

    def over_quota_customers(self):
        """Customers whose stored data already exceeds their storage quota."""
        return [c for c, q in self.quotas.items()
                if self.usage_gb.get(c, 0.0) > q.max_storage_gb]
