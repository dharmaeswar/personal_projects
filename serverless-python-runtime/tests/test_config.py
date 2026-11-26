import pytest

from runtime.config import RuntimeConfig


def test_defaults_are_valid():
    RuntimeConfig().validate()


def test_memory_bounds():
    with pytest.raises(ValueError):
        RuntimeConfig(memory_mb=64).validate()
    with pytest.raises(ValueError):
        RuntimeConfig(memory_mb=20000).validate()


def test_timeout_bounds():
    with pytest.raises(ValueError):
        RuntimeConfig(timeout_s=0).validate()
    with pytest.raises(ValueError):
        RuntimeConfig(timeout_s=901).validate()


def test_concurrency_bounds():
    with pytest.raises(ValueError):
        RuntimeConfig(max_concurrency=0).validate()


def test_bundle_budget_bounds():
    with pytest.raises(ValueError):
        RuntimeConfig(bundle_budget_mb=0).validate()


def test_python_version():
    with pytest.raises(ValueError):
        RuntimeConfig(python_version="2.7").validate()
    RuntimeConfig(python_version="3.13").validate()


def test_as_dict_round_trip():
    cfg = RuntimeConfig(memory_mb=1024, timeout_s=60)
    assert cfg.as_dict()["memory_mb"] == 1024
    assert cfg.as_dict()["timeout_s"] == 60
