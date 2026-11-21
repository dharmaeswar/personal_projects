from gateway.auth import ApiKey
from gateway.ratelimit import RateLimiter, TokenBucket


def test_bucket_allows_within_capacity():
    bucket = TokenBucket(10, 1.0, now=1000.0)
    assert bucket.try_consume(10, now=1000.0) is True
    assert bucket.try_consume(1, now=1000.0) is False


def test_bucket_refills_over_time():
    bucket = TokenBucket(10, 1.0, now=1000.0)
    assert bucket.try_consume(10, now=1000.0) is True
    assert bucket.try_consume(5, now=1005.0) is True  # 5s * 1/s refilled
    assert bucket.try_consume(1, now=1005.0) is False


def test_retry_after_reports_wait():
    bucket = TokenBucket(10, 2.0, now=1000.0)
    bucket.try_consume(10, now=1000.0)
    assert bucket.retry_after_seconds(4, now=1000.0) == 2.0


def _key(tier="free"):
    return ApiKey("k1", "acme", tier, ("models:invoke",))


def test_limiter_rejects_over_request_budget_without_consuming():
    limiter = RateLimiter(budgets={"free": (2, 10_000)})
    key = _key()
    assert limiter.check(key, 10, now=1000.0)[0] is True
    assert limiter.check(key, 10, now=1000.0)[0] is True
    allowed, wait = limiter.check(key, 10, now=1000.0)
    assert allowed is False and wait > 0
    # A rejected request consumed nothing: after 60s the bucket is full again.
    assert limiter.check(key, 10, now=1060.0)[0] is True


def test_limiter_rejects_over_token_budget():
    limiter = RateLimiter(budgets={"free": (600, 100)})
    key = _key()
    allowed, _ = limiter.check(key, 101, now=1000.0)
    assert allowed is False
    allowed, _ = limiter.check(key, 100, now=1000.0)
    assert allowed is True
