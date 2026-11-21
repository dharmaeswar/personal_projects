"""Tests for the serving endpoints wired into the Gateway."""

from gateway.api import Gateway
from gateway.serving import ModelVersion

SPEC = {"name": "churn-risk", "version": "1.2.0", "framework": "scikit-learn",
        "features": [{"name": "tenure_months", "type": "number",
                      "required": True, "minimum": 0, "maximum": 600}],
        "target": "churn_probability"}


def make_gateway():
    gateway = Gateway()
    gateway.keys.add_seeded("sk-test-1", "test", "pro",
                            ("models:invoke", "usage:read", "billing:read"))
    return gateway


def test_register_list_predict_round_trip():
    gateway = make_gateway()
    status, created = gateway.register_model("sk-test-1", SPEC)
    assert status == 201
    assert created["name"] == "churn-risk"
    assert created["version"] == "1.2.0"
    status, listed = gateway.list_models("sk-test-1")
    assert status == 200
    assert listed["models"][0]["name"] == "churn-risk"
    assert listed["models"][0]["latest"] == "1.2.0"
    status, payload = gateway.predict("sk-test-1", "churn-risk",
                                      {"tenure_months": 12})
    assert status == 200
    assert payload["model"] == "churn-risk"
    status, metrics = gateway.serving_metrics("sk-test-1")
    assert status == 200
    assert metrics["serving"]["churn-risk"]["requests"] == 1


def test_register_duplicate_returns_400():
    gateway = make_gateway()
    assert gateway.register_model("sk-test-1", SPEC)[0] == 201
    status, payload = gateway.register_model("sk-test-1", SPEC)
    assert status == 400
    assert payload["error"] == "invalid_model_spec"


def test_register_bad_spec_returns_400():
    gateway = make_gateway()
    status, payload = gateway.register_model("sk-test-1", {"name": "x"})
    assert status == 400


def test_serving_endpoints_require_auth():
    gateway = make_gateway()
    gateway.register_model("sk-test-1", SPEC)
    assert gateway.list_models("bad-key")[0] == 401
    assert gateway.predict("bad-key", "churn-risk", {"tenure_months": 12})[0] == 401
    assert gateway.register_model("bad-key", SPEC)[0] == 401
    assert gateway.serving_metrics("bad-key")[0] == 401


def test_predict_unknown_model_404():
    gateway = make_gateway()
    status, payload = gateway.predict("sk-test-1", "ghost", {})
    assert status == 404
    assert payload["error"] == "unknown_model"


def test_seeded_demo_model_scores():
    from run_service import build_gateway
    gateway = build_gateway()
    gateway.keys.add_seeded("sk-test-1", "test", "pro", ("models:invoke",))
    status, payload = gateway.predict(
        "sk-test-1", "churn-risk",
        {"tenure_months": 24, "monthly_spend": 450,
         "support_tickets": 1, "is_enterprise": False})
    assert status == 200
    assert payload["version"] == "1.2.0"
    assert 0.0 <= payload["prediction"] <= 1.0
