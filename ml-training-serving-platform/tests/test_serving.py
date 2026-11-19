import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ml_platform.data import generate_applications
from ml_platform.registry import Registry
from ml_platform.serving import ServingService
from ml_platform.training import train_pipeline


@pytest.fixture
def service(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    model, metrics, train_rows = train_pipeline(n_train=800, n_test=200, seed=42)
    v1 = registry.register("credit-decision", model, metrics)
    registry.promote(v1)
    model2, metrics2, _ = train_pipeline(n_train=800, n_test=200, seed=123)
    v2 = registry.register("credit-decision", model2, metrics2)
    svc = ServingService(registry, train_rows)
    return svc, registry, v1, v2


def _features(seed=1):
    return generate_applications(1, seed=seed)[0][0]


def test_predict_returns_production_version_and_decision(service):
    svc, _, v1, _ = service
    result = svc.predict("app-1", _features())
    assert result["version"] == v1
    assert result["decision"] in ("approve", "decline")
    assert 0.0 <= result["default_probability"] <= 1.0


def test_canary_routes_a_share_and_is_deterministic_per_id(service):
    svc, _, v1, v2 = service
    svc.start_canary(v2, share=0.5)
    versions = {svc.predict(f"app-{i}", _features(seed=i))["version"] for i in range(200)}
    assert versions == {v1, v2}  # both versions got traffic
    first = svc.predict("app-42", _features(seed=42))["version"]
    second = svc.predict("app-42", _features(seed=42))["version"]
    assert first == second  # same id always routes the same way


def test_canary_share_validation(service):
    svc, _, _, v2 = service
    with pytest.raises(ValueError):
        svc.start_canary(v2, share=0)
    with pytest.raises(ValueError):
        svc.start_canary("no-such-version", share=0.5)


def test_latency_stats_and_error_rate_track_requests(service):
    svc, _, _, _ = service
    for i in range(10):
        svc.predict(f"app-{i}", _features(seed=i))
    stats = svc.latency_stats()
    assert stats["count"] == 10
    assert stats["mean_ms"] >= 0
    assert stats["p95_ms"] >= 0
    assert svc.error_rate() == 0.0


def test_predict_with_no_production_model_raises_and_counts_error(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    _, _, train_rows = train_pipeline(n_train=200, n_test=50, seed=42)
    svc = ServingService(registry, train_rows)
    with pytest.raises(ValueError):
        svc.predict("app-1", _features())
    assert svc.error_rate() == 1.0


def test_drift_report_flags_shifted_features(service):
    svc, _, _, _ = service
    # Feed traffic with a very different debt-ratio distribution.
    shifted = {"income": 40000, "debt_ratio": 0.85, "credit_history_years": 1,
               "delinquencies": 3, "amount": 24000}
    for i in range(60):
        svc.predict(f"drift-{i}", shifted)
    report = svc.drift_report()
    assert report["debt_ratio"]["flagged"] is True
    assert report["debt_ratio"]["psi"] > 0.25


def test_rollback_restores_previous_production_and_stops_canary(service):
    svc, registry, v1, v2 = service
    registry.promote(v2)
    svc.start_canary(v1, share=0.5)
    assert svc.rollback() == v1
    assert registry.production_version() == v1
    assert svc.canary_version is None
