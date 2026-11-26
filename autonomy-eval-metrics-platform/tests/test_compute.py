import pytest

from eval_platform.compute import MetricComputer, aggregate


def test_aggregate_functions():
    assert aggregate([1, 2, 3, 4], "mean") == 2.5
    assert aggregate([1, 2, 3], "count") == 3.0
    assert aggregate([1, 9], "max") == 9
    assert aggregate([1, 0, 1, 0], "rate") == 0.5
    assert aggregate(list(range(1, 101)), "p95") == 95
    assert aggregate([], "mean") is None
    with pytest.raises(ValueError):
        aggregate([1], "median")


def test_idempotent_compute():
    comp = MetricComputer()
    r1 = comp.compute("run1", "m", 1, "highway", [1, 0, 0], "rate", 3)
    r2 = comp.compute("run1", "m", 1, "highway", [1, 0, 0], "rate", 3)
    assert r1 is r2
    assert comp.results_for_run("run1") == [r1]


def test_changed_inputs_recompute():
    comp = MetricComputer()
    r1 = comp.compute("run1", "m", 1, "highway", [1, 0, 0], "rate", 3)
    r2 = comp.compute("run1", "m", 1, "highway", [1, 1, 0], "rate", 3)
    assert r2 is not r1 and r2.value == pytest.approx(2 / 3)


def test_coverage_and_backfill_tag():
    comp = MetricComputer()
    r = comp.compute("run1", "m", 1, "urban", [0, 0], "rate", 10)
    assert r.coverage == 0.2 and r.sample_size == 2 and r.backfill_id is None
    out = comp.backfill("run1", "m", 1, {"urban": [0, 0, 1]}, "rate", 10, "bf-1")
    assert out[0].backfill_id == "bf-1" and out[0].value == pytest.approx(1 / 3)
