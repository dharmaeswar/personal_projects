import pytest

from eval_platform.registry import MetricRegistry


def test_register_versions_metrics():
    reg = MetricRegistry()
    v1 = reg.register("intervention_rate", "desc", "rate", "rate")
    v2 = reg.register("intervention_rate", "desc v2", "rate", "rate")
    assert v1.version == 1 and v2.version == 2
    assert reg.latest("intervention_rate") is v2
    assert reg.get("intervention_rate", 1) is v1
    assert reg.get("missing", 1) is None
    assert reg.names() == ["intervention_rate"]


def test_bad_aggregation_rejected():
    reg = MetricRegistry()
    with pytest.raises(ValueError):
        reg.register("m", "d", "u", "median")


def test_deprecate_marks_version():
    reg = MetricRegistry()
    reg.register("m", "d", "u", "mean")
    dep = reg.deprecate("m", 1)
    assert dep.deprecated is True
    assert reg.latest("m").deprecated is True
    with pytest.raises(ValueError):
        reg.deprecate("m", 9)
