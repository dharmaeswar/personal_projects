import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ml_platform.registry import Registry
from ml_platform.training import train_pipeline


@pytest.fixture
def registry(tmp_path):
    return Registry(str(tmp_path / "registry.json"))


@pytest.fixture
def model_and_metrics():
    model, metrics, _ = train_pipeline(n_train=500, n_test=100, seed=42)
    return model, metrics


def test_register_starts_in_staging(registry, model_and_metrics):
    model, metrics = model_and_metrics
    version = registry.register("credit-decision", model, metrics)
    assert registry.get(version)["stage"] == "staging"
    assert registry.production_version() is None


def test_promote_moves_to_production_and_archives_previous(registry, model_and_metrics):
    model, metrics = model_and_metrics
    v1 = registry.register("credit-decision", model, metrics)
    v2 = registry.register("credit-decision", model, metrics)
    registry.promote(v1)
    assert registry.production_version() == v1
    registry.promote(v2)
    assert registry.production_version() == v2
    assert registry.get(v1)["stage"] == "archived"


def test_rollback_restores_previous_production(registry, model_and_metrics):
    model, metrics = model_and_metrics
    v1 = registry.register("credit-decision", model, metrics)
    v2 = registry.register("credit-decision", model, metrics)
    registry.promote(v1)
    registry.promote(v2)
    assert registry.rollback() == v1
    assert registry.production_version() == v1


def test_rollback_with_no_previous_returns_none(registry, model_and_metrics):
    model, metrics = model_and_metrics
    v1 = registry.register("credit-decision", model, metrics)
    registry.promote(v1)
    assert registry.rollback() is None


def test_duplicate_version_rejected_and_unknown_promote_fails(registry, model_and_metrics):
    model, metrics = model_and_metrics
    registry.register("credit-decision", model, metrics, version="credit-decision-v1")
    with pytest.raises(ValueError):
        registry.register("credit-decision", model, metrics, version="credit-decision-v1")
    with pytest.raises(ValueError):
        registry.promote("credit-decision-v99")


def test_registry_persists_across_instances(tmp_path, model_and_metrics):
    model, metrics = model_and_metrics
    path = str(tmp_path / "registry.json")
    reg = Registry(path)
    v1 = reg.register("credit-decision", model, metrics)
    reg.promote(v1)
    reg2 = Registry(path)
    assert reg2.production_version() == v1
    assert reg2.get(v1)["metrics"] == metrics
