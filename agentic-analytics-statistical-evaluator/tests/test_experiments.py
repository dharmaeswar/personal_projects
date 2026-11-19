"""Tests for the product experimentation module."""

import math

from agentic_stats import experiments
from agentic_stats.data import build_dataset


def test_norm_ppf_known_values():
    assert abs(experiments.norm_ppf(0.5)) < 1e-9
    assert abs(experiments.norm_ppf(0.975) - 1.96) < 0.01
    assert abs(experiments.norm_ppf(0.025) + 1.96) < 0.01
    assert abs(experiments.norm_ppf(0.80) - 0.8416) < 0.01
    assert abs(experiments.norm_ppf(0.995) - 2.5758) < 0.01


def test_norm_ppf_rejects_invalid_p():
    for bad in (0.0, 1.0, -0.1, 1.5):
        try:
            experiments.norm_ppf(bad)
        except ValueError:
            continue
        raise AssertionError(f"norm_ppf({bad}) should raise ValueError")


def test_required_sample_size_known_values():
    # Textbook: d = 0.5, alpha 0.05, power 0.80 needs ~64 per arm.
    n = experiments.required_sample_size(0.5)
    assert 60 <= n <= 66
    # A bigger effect needs fewer users; higher power needs more.
    assert experiments.required_sample_size(1.0) < n
    assert experiments.required_sample_size(0.5, power=0.90) > n
    assert experiments.required_sample_size(0.2) > 300


def test_required_sample_size_rejects_bad_inputs():
    for kwargs in ({"effect_size": 0.0}, {"effect_size": -0.5},
                   {"effect_size": 0.5, "alpha": 1.5},
                   {"effect_size": 0.5, "power": 0.0}):
        try:
            experiments.required_sample_size(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"required_sample_size({kwargs}) should raise ValueError")


def test_design_experiment_shape_and_duration():
    design = experiments.design_experiment(baseline_std=10.0, mde=5.0, daily_users=1000)
    assert design["n_per_arm"] == experiments.required_sample_size(0.5)
    assert design["total_users"] == 2 * design["n_per_arm"]
    assert design["days_to_run"] == math.ceil(design["total_users"] / 1000)
    assert design["days_to_run"] == 1


def test_design_experiment_slow_traffic_takes_longer():
    fast = experiments.design_experiment(10.0, 5.0, daily_users=1000)
    slow = experiments.design_experiment(10.0, 5.0, daily_users=10)
    assert slow["days_to_run"] > fast["days_to_run"]


def test_guardrail_passes_when_no_regression():
    control = [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 100.0, 101.0]
    treatment = [100.0, 99.0, 101.0, 100.0, 99.0, 101.0, 100.0, 100.0]
    result = experiments.guardrail_check(control, treatment, max_regression=5.0)
    assert result["verdict"] == "PASS"
    assert result["breached"] is False


def test_guardrail_fails_on_large_significant_regression():
    control = [100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0,
               100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1]
    treatment = [80.0, 80.1, 79.9, 80.0, 80.1, 79.9, 80.0, 80.1, 79.9, 80.0,
                 80.1, 79.9, 80.0, 80.1, 79.9, 80.0, 80.1, 79.9, 80.0, 80.1]
    result = experiments.guardrail_check(control, treatment, max_regression=5.0)
    assert result["verdict"] == "FAIL"
    assert result["breached"] is True
    assert result["significant"] is True


def test_guardrail_passes_on_small_noisy_drop():
    # A 6-unit drop that is pure noise (huge variance) must not fail the
    # guardrail: a fail needs both a breach and statistical significance.
    control = [100.0, 60.0, 140.0, 90.0, 110.0, 70.0, 130.0, 100.0]
    treatment = [94.0, 54.0, 134.0, 84.0, 104.0, 64.0, 124.0, 94.0]
    result = experiments.guardrail_check(control, treatment, max_regression=5.0)
    assert result["verdict"] == "PASS"


def test_obrien_fleming_boundaries_decrease():
    bounds = experiments.obrien_fleming_boundaries(4)
    assert len(bounds) == 4
    assert bounds[0] > bounds[1] > bounds[2] > bounds[3]
    assert bounds[0] > 1.96  # first look needs stronger evidence
    assert abs(bounds[-1] - 1.96) < 0.05  # final look is near the usual value
    assert experiments.obrien_fleming_boundaries(1) == [1.96]


def test_sequential_decision_stops_at_first_crossing():
    bounds = experiments.obrien_fleming_boundaries(4)
    decision = experiments.sequential_decision([1.0, 5.0, 1.0, 1.0], bounds)
    assert decision["stop_at_look"] == 2
    never = experiments.sequential_decision([0.5, 0.5, 0.5, 0.5], bounds)
    assert never["stop_at_look"] is None


def test_sequential_decision_rejects_mismatched_lengths():
    try:
        experiments.sequential_decision([1.0], [1.96, 1.96])
    except ValueError:
        return
    raise AssertionError("mismatched lengths should raise ValueError")


def test_experiment_readout_on_demo_dataset():
    rows = build_dataset()
    readout = experiments.experiment_readout(rows)
    assert readout["n_per_arm"] == 120
    assert readout["significant"] is True
    assert readout["mean_diff"] > 5.0
    assert readout["ci_95"][0] > 0
    assert readout["power"] > 0.9
    assert readout["guardrail"]["verdict"] == "PASS"


def test_experiment_readout_flags_underpowered_mde():
    rows = build_dataset()
    # A tiny MDE needs far more than 120 users per arm.
    readout = experiments.experiment_readout(rows, mde=1.0)
    assert readout["adequately_powered"] is False
    assert readout["required_n_per_arm"] > 120


def test_build_experiment_section_contains_key_content():
    rows = build_dataset()
    section = experiments.build_experiment_section(rows)
    for text in [
        "PRODUCT EXPERIMENTATION",
        "Primary outcome:",
        "Power:",
        "Verdict: SHIP",
        "O'Brien-Fleming boundaries",
    ]:
        assert text in section
