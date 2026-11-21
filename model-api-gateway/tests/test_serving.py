"""Tests for predictive-model serving: registry, validation, scoring, metrics."""

import pytest

from gateway.serving import (FeatureSpec, ModelRegistry, ModelVersion,
                             Scorer, ServingMetrics, demo_score)


def churn_model(version="1.2.0"):
    return ModelVersion(
        "churn-risk", version, "scikit-learn",
        [{"name": "tenure_months", "type": "number", "required": True,
          "minimum": 0, "maximum": 600},
         {"name": "monthly_spend", "type": "number", "required": True,
          "minimum": 0, "maximum": 100000},
         {"name": "support_tickets", "type": "number", "required": True,
          "minimum": 0, "maximum": 100},
         {"name": "is_enterprise", "type": "boolean", "required": False}],
        "churn_probability")


def valid_features():
    return {"tenure_months": 24, "monthly_spend": 450,
            "support_tickets": 1, "is_enterprise": False}


def test_register_and_latest_version():
    registry = ModelRegistry()
    registry.register(churn_model("1.1.0"))
    registry.register(churn_model("1.2.0"))
    assert registry.get("churn-risk").version == "1.2.0"
    assert registry.get("churn-risk", "1.1.0").version == "1.1.0"
    assert registry.get("churn-risk", "9.9.9") is None
    assert registry.get("no-such-model") is None


def test_duplicate_version_rejected():
    registry = ModelRegistry()
    registry.register(churn_model("1.2.0"))
    with pytest.raises(ValueError):
        registry.register(churn_model("1.2.0"))


def test_version_ordering_numeric_not_lexical():
    registry = ModelRegistry()
    registry.register(churn_model("1.9.0"))
    registry.register(churn_model("1.10.0"))
    assert registry.get("churn-risk").version == "1.10.0"


def test_models_list():
    registry = ModelRegistry()
    registry.register(churn_model("1.1.0"))
    registry.register(churn_model("1.2.0"))
    listed = registry.models()
    assert listed == [{"name": "churn-risk", "versions": ["1.1.0", "1.2.0"],
                       "latest": "1.2.0", "framework": "scikit-learn",
                       "target": "churn_probability"}]


def test_feature_spec_rejects_bad_type_and_bounds():
    with pytest.raises(ValueError):
        FeatureSpec("x", type="date")
    with pytest.raises(ValueError):
        FeatureSpec("x", minimum=10, maximum=1)


def test_validation_accepts_valid_input():
    registry = ModelRegistry()
    registry.register(churn_model())
    assert registry.validate(churn_model(), valid_features()) == []


def test_validation_missing_required_and_wrong_type():
    registry = ModelRegistry()
    registry.register(churn_model())
    bad = {"tenure_months": "two years", "monthly_spend": 450}
    errors = registry.validate(churn_model(), bad)
    assert any("must be a number" in e for e in errors)
    assert any("missing required feature: support_tickets" in e for e in errors)


def test_validation_rejects_out_of_range_and_unknown():
    registry = ModelRegistry()
    registry.register(churn_model())
    features = dict(valid_features(), tenure_months=-5, nickname="x")
    errors = registry.validate(churn_model(), features)
    assert any("below minimum" in e for e in errors)
    assert any("unknown feature: nickname" in e for e in errors)


def test_validation_rejects_non_object():
    registry = ModelRegistry()
    registry.register(churn_model())
    assert registry.validate(churn_model(), [1, 2]) == [
        "features must be a JSON object"]


def test_optional_feature_may_be_omitted():
    registry = ModelRegistry()
    registry.register(churn_model())
    features = valid_features()
    del features["is_enterprise"]
    assert registry.validate(churn_model(), features) == []


def test_score_success_returns_version_and_prediction():
    scorer = Scorer(ModelRegistry())
    scorer.registry.register(churn_model())
    status, payload = scorer.score("churn-risk", valid_features())
    assert status == 200
    assert payload["version"] == "1.2.0"
    assert payload["target"] == "churn_probability"
    assert 0.0 <= payload["prediction"] <= 1.0
    assert payload["latency_ms"] == 13.0  # 5ms base + 2ms x 4 features


def test_score_is_deterministic():
    scorer = Scorer(ModelRegistry())
    scorer.registry.register(churn_model())
    _, first = scorer.score("churn-risk", valid_features())
    _, second = scorer.score("churn-risk", valid_features())
    assert first["prediction"] == second["prediction"]
    assert first["prediction"] == round(demo_score(churn_model(), valid_features()), 6)


def test_score_pinned_version():
    scorer = Scorer(ModelRegistry())
    scorer.registry.register(churn_model("1.1.0"))
    scorer.registry.register(churn_model("1.2.0"))
    _, payload = scorer.score("churn-risk", valid_features(), version="1.1.0")
    assert payload["version"] == "1.1.0"


def test_score_unknown_model_404():
    scorer = Scorer(ModelRegistry())
    status, payload = scorer.score("no-such-model", valid_features())
    assert status == 404
    assert payload["error"] == "unknown_model"


def test_score_invalid_input_422_with_details():
    scorer = Scorer(ModelRegistry())
    scorer.registry.register(churn_model())
    status, payload = scorer.score("churn-risk", {"tenure_months": -1})
    assert status == 422
    assert payload["error"] == "validation_failed"
    assert payload["details"]


def test_serving_metrics_track_latency_and_errors():
    metrics = ServingMetrics()
    scorer = Scorer(ModelRegistry(), metrics)
    scorer.registry.register(churn_model())
    scorer.score("churn-risk", valid_features())
    scorer.score("churn-risk", valid_features())
    scorer.score("churn-risk", {"tenure_months": -1})
    summary = metrics.summary("churn-risk")
    assert summary["requests"] == 3
    assert summary["errors"] == 1
    assert summary["p50_ms"] == 13.0
    assert summary["p95_ms"] == 13.0
    slo = metrics.evaluate_slo("churn-risk")
    assert slo["ok"] is False  # 1/3 errors exceeds the 1% error budget
    assert any("error_rate_breach" in a for a in slo["alerts"])
