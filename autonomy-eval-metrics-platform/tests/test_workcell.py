"""Tests for the workcell / equipment performance simulation."""

import pytest

from eval_platform import EvalMetricsPlatform
from eval_platform.workcell import (
    publish_workcell_metrics,
    simulate_workcell_cycles,
    workcell_metrics,
)


def test_simulation_is_deterministic():
    a = simulate_workcell_cycles(seed=7, n_cycles=100)
    b = simulate_workcell_cycles(seed=7, n_cycles=100)
    assert a == b
    assert len(a) == 100
    assert all(10.5 <= c.cycle_time_s <= 13.5 for c in a)


def test_simulation_faults_add_downtime():
    cycles = simulate_workcell_cycles(seed=7, n_cycles=500)
    faulted = [c for c in cycles if c.faulted]
    assert faulted, "seed 7 should produce some faults in 500 cycles"
    assert all(c.downtime_s == 45.0 for c in faulted)
    assert all(c.downtime_s == 0.0 for c in cycles if not c.faulted)


def test_simulation_rejects_bad_inputs():
    with pytest.raises(ValueError):
        simulate_workcell_cycles(n_cycles=0)
    with pytest.raises(ValueError):
        simulate_workcell_cycles(fault_rate=1.5)


def test_metrics_math_on_known_cycles():
    from eval_platform.workcell import WorkcellCycle
    cycles = [WorkcellCycle(i, 10.0, False) for i in range(9)]
    cycles.append(WorkcellCycle(9, 20.0, True, 45.0))
    m = workcell_metrics(cycles)
    assert m["mean_cycle_s"] == 11.0
    assert m["p95_cycle_s"] == 20.0
    assert m["fault_rate"] == 0.1
    # 10 cycles, 110 s productive + 45 s downtime = 155 s total.
    assert m["throughput_per_hour"] == pytest.approx(3600 / 15.5, rel=1e-3)
    assert m["availability"] == pytest.approx(110 / 155, rel=1e-3)


def test_metrics_empty_input():
    m = workcell_metrics([])
    assert all(v is None for v in m.values())


def test_publish_goes_through_platform_and_is_idempotent():
    platform = EvalMetricsPlatform()
    cycles = simulate_workcell_cycles(seed=7, n_cycles=200)
    first = publish_workcell_metrics(platform, "run-wc-001", cycles)
    assert set(first) == {"cycle_time_mean", "cycle_time_p95",
                          "workcell_fault_rate"}
    assert first["cycle_time_mean"].value == pytest.approx(12.0, abs=0.2)
    assert first["workcell_fault_rate"].value == pytest.approx(
        sum(1 for c in cycles if c.faulted) / 200, rel=1e-6)
    # Second publish with the same inputs returns the same stored results.
    second = publish_workcell_metrics(platform, "run-wc-001", cycles)
    assert second["cycle_time_mean"] is first["cycle_time_mean"]
    assert second["workcell_fault_rate"] is first["workcell_fault_rate"]


def test_publish_matches_standalone_metrics():
    platform = EvalMetricsPlatform()
    cycles = simulate_workcell_cycles(seed=11, n_cycles=300)
    published = publish_workcell_metrics(platform, "run-wc-002", cycles)
    standalone = workcell_metrics(cycles)
    # Standalone summary rounds to 3-4 decimals; platform keeps full
    # precision, so compare with a rounding-sized tolerance.
    assert published["cycle_time_mean"].value == pytest.approx(
        standalone["mean_cycle_s"], abs=0.001)
    assert published["cycle_time_p95"].value == pytest.approx(
        standalone["p95_cycle_s"], abs=0.001)
    assert published["workcell_fault_rate"].value == pytest.approx(
        standalone["fault_rate"], abs=0.0001)
