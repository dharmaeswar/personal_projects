import math
import pytest
from model_validation_toolkit import backtest_summary, sensitivity_table, mean_drift_bps, population_stability_index


def test_backtest_summary_perfect_model():
    s = backtest_summary([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert s["bias"] == 0.0 and s["rmse"] == 0.0 and s["hit_rate_5pct"] == 1.0


def test_backtest_summary_bias():
    s = backtest_summary([11.0, 12.0], [10.0, 10.0])
    assert s["bias"] == pytest.approx(1.5)


def test_backtest_summary_rejects_mismatch():
    with pytest.raises(ValueError):
        backtest_summary([1.0], [1.0, 2.0])


def test_sensitivity_table_linear_model():
    table = sensitivity_table(lambda x: 2.0 * x, 1.0, bumps=(-0.01, 0.0, 0.01))
    assert table[0.0] == 0.0
    assert table[0.01] == pytest.approx(0.02)
    assert table[-0.01] == pytest.approx(-0.02)


def test_mean_drift_bps():
    assert mean_drift_bps([100.0, 100.0], [100.3, 100.3]) == pytest.approx(30.0)


def test_psi_zero_for_identical_distributions():
    assert population_stability_index([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0.0)


def test_psi_positive_for_shifted_distribution():
    assert population_stability_index([0.5, 0.5], [0.9, 0.1]) > 0.25
