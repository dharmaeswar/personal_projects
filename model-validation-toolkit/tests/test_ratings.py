"""Tests for rating-model and criteria validation (ratings.py).

All data is synthetic and seeded; no real ratings or obligors are used.
"""

import pytest

from model_validation_toolkit.ratings import (
    check_pd_monotonicity,
    data_aging_check,
    default_rate_backtest,
    grade_backtest_table,
    migration_summary,
    transition_matrix_stability,
)

GRADES = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]


def test_pd_monotonicity_passes_for_rising_pds():
    result = check_pd_monotonicity(
        [("AAA", 0.0002), ("AA", 0.0005), ("A", 0.001), ("BBB", 0.004),
         ("BB", 0.015), ("B", 0.05), ("CCC", 0.20)])
    assert result["monotone"] is True
    assert result["inversions"] == []
    assert result["n_grades"] == 7


def test_pd_monotonicity_flags_inversion():
    result = check_pd_monotonicity(
        [("AAA", 0.0002), ("AA", 0.001), ("A", 0.0005), ("BBB", 0.004)])
    assert result["monotone"] is False
    assert len(result["inversions"]) == 1
    inv = result["inversions"][0]
    assert inv["better_grade"] == "AA" and inv["worse_grade"] == "A"


def test_pd_monotonicity_rejects_bad_inputs():
    with pytest.raises(ValueError):
        check_pd_monotonicity([("AAA", 0.0002)])
    with pytest.raises(ValueError):
        check_pd_monotonicity([("AAA", -0.1), ("AA", 0.001)])


def test_default_backtest_passes_when_realised_matches_pd():
    # 1000 obligors at 1% PD: 10 defaults expected, 11 observed.
    result = default_rate_backtest(0.01, 11, 1000)
    assert result["expected_defaults"] == pytest.approx(10.0)
    assert abs(result["z"]) < 0.5
    assert result["pass"] is True


def test_default_backtest_fails_when_defaults_far_exceed_pd():
    # 1000 obligors at 1% PD: 30 defaults observed is far outside.
    result = default_rate_backtest(0.01, 30, 1000)
    assert result["z"] > 6.0
    assert result["p_value"] < 0.001
    assert result["pass"] is False


def test_default_backtest_rejects_bad_inputs():
    with pytest.raises(ValueError):
        default_rate_backtest(0.0, 0, 100)
    with pytest.raises(ValueError):
        default_rate_backtest(0.01, 0, 0)
    with pytest.raises(ValueError):
        default_rate_backtest(0.01, 101, 100)


def test_grade_backtest_table_reports_failing_grades():
    table = grade_backtest_table([
        ("AAA", 0.0002, 0, 500),
        ("BBB", 0.004, 4, 1000),
        ("B", 0.05, 90, 1000),
    ])
    assert table["n_grades"] == 3
    assert table["failing_grades"] == ["B"]
    assert table["all_pass"] is False
    assert table["grades"][0]["grade"] == "AAA"


def test_transition_stability_passes_for_small_moves():
    prior = [[0.9, 0.08, 0.02], [0.05, 0.85, 0.10], [0.0, 0.05, 0.95]]
    current = [[0.91, 0.07, 0.02], [0.05, 0.86, 0.09], [0.0, 0.05, 0.95]]
    result = transition_matrix_stability(prior, current)
    assert result["stable"] is True
    assert result["max_abs_diff"] == pytest.approx(0.01)
    assert result["breached_cells"] == []


def test_transition_stability_flags_large_move():
    prior = [[0.9, 0.08, 0.02], [0.05, 0.85, 0.10], [0.0, 0.05, 0.95]]
    current = [[0.80, 0.15, 0.05], [0.05, 0.85, 0.10], [0.0, 0.05, 0.95]]
    result = transition_matrix_stability(prior, current, threshold=0.05)
    assert result["stable"] is False
    assert len(result["breached_cells"]) == 2
    assert result["max_abs_diff"] == pytest.approx(0.10)


def test_transition_stability_rejects_mismatched_shapes():
    with pytest.raises(ValueError):
        transition_matrix_stability([[0.9, 0.1]], [[0.9, 0.1], [0.1, 0.9]])


def test_data_aging_flags_stale_inputs():
    result = data_aging_check(
        {"financials": "2026-10-01", "market_data": "2026-11-20",
         "criteria_text": "2026-01-15"},
        as_of="2026-11-23", max_age_days=90)
    assert result["all_fresh"] is False
    assert [s["input"] for s in result["stale_inputs"]] == ["criteria_text"]
    assert result["max_age_days"] == 312


def test_data_aging_passes_when_all_fresh():
    result = data_aging_check(
        {"financials": "2026-10-01", "market_data": "2026-11-20"},
        as_of="2026-11-23", max_age_days=90)
    assert result["all_fresh"] is True
    assert result["stale_inputs"] == []


def test_data_aging_rejects_future_vintage():
    with pytest.raises(ValueError):
        data_aging_check({"financials": "2026-12-01"}, as_of="2026-11-23")


def test_migration_summary_rates():
    counts = {
        ("AAA", "AAA"): 90, ("AAA", "AA"): 10,
        ("AA", "AAA"): 5, ("AA", "AA"): 85, ("AA", "A"): 10,
        ("A", "AA"): 8, ("A", "A"): 80, ("A", "BBB"): 10,
        ("A", "Default"): 2,
    }
    result = migration_summary(counts, ["AAA", "AA", "A", "BBB"])
    assert result["total_obligors"] == 300
    assert result["upgrade_rate"] == pytest.approx(13 / 300)
    assert result["downgrade_rate"] == pytest.approx(30 / 300)
    assert result["default_rate"] == pytest.approx(2 / 300)
    assert result["stable_rate"] == pytest.approx(255 / 300)


def test_migration_summary_rejects_bad_inputs():
    with pytest.raises(ValueError):
        migration_summary({}, ["AAA", "AA"])
    with pytest.raises(ValueError):
        migration_summary({("AAA", "ZZZ"): 1}, ["AAA", "AA"])
    with pytest.raises(ValueError):
        migration_summary({("AAA", "AA"): -1}, ["AAA", "AA"])
