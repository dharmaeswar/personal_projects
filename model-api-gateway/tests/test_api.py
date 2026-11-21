"""End-to-end tests through Gateway.invoke / usage_for / billing_for."""

from gateway.api import Gateway
from gateway.router import Backend


def _gateway():
    gateway = Gateway()
    raw, _ = gateway.keys.mint("acme", "pro",
                               ("models:invoke", "usage:read", "billing:read"))
    gateway.registry.register(Backend("gpu-1", "llama-4-scout", 100.0, 4))
    return gateway, raw


def test_invoke_success_meters_and_bills():
    gateway, raw = _gateway()
    status, payload = gateway.invoke(raw, "llama-4-scout",
                                     "Summarize freight rail delays.", max_tokens=64)
    assert status == 200
    assert payload["backend"] == "gpu-1"
    assert payload["usage"]["prompt_tokens"] > 0
    status, usage = gateway.usage_for(raw)
    assert status == 200 and usage["usage"]["llama-4-scout"]["requests"] == 1
    status, invoice = gateway.billing_for(raw)
    assert status == 200 and invoice["total_usd"] > 0


def test_invoke_rejects_bad_key():
    gateway, _ = _gateway()
    status, payload = gateway.invoke("sk-nope", "llama-4-scout", "hi")
    assert status == 401 and payload["error"] == "unknown_key"


def test_invoke_rejects_unknown_model():
    gateway, raw = _gateway()
    status, payload = gateway.invoke(raw, "gpt-nope", "hi")
    assert status == 404 and payload["error"] == "unknown_model"


def test_invoke_rate_limits_small_budget():
    gateway, raw = _gateway()
    gateway.limiter = __import__("gateway.ratelimit", fromlist=["RateLimiter"]).RateLimiter(
        budgets={"pro": (1, 10)})
    status, _ = gateway.invoke(raw, "llama-4-scout", "hi", now=1000.0)
    assert status == 200
    status, payload = gateway.invoke(raw, "llama-4-scout", "hi", now=1000.0)
    assert status == 429 and payload["retry_after_seconds"] > 0


def test_usage_requires_scope():
    gateway = Gateway()
    raw, _ = gateway.keys.mint("acme", "pro", ("models:invoke",))
    gateway.registry.register(Backend("gpu-1", "llama-4-scout", 100.0, 4))
    status, payload = gateway.usage_for(raw)
    assert status == 401 and payload["error"] == "insufficient_scope"
