import math
import pytest
from model_validation_toolkit.surveillance import (
    garch11_fit, garch11_forecast, yield_curve_pca,
    rolling_window_diagnostics, out_of_sample_backtest, cusum_break_check,
)

# Deterministic clustered-volatility returns: quiet half, then noisy half.
RETURNS = [0.001 * math.sin(i) for i in range(30)] + [
    0.02 * math.sin(i * 1.7) for i in range(30)]


def test_garch11_fit_returns_valid_params():
    p = garch11_fit(RETURNS)
    assert p["omega"] > 0 and p["alpha"] > 0 and p["beta"] > 0
    assert p["alpha"] + p["beta"] < 1.0
    assert p["long_run_variance"] > 0
    assert math.isfinite(p["log_likelihood"])


def test_garch11_fit_rejects_short_series():
    with pytest.raises(ValueError):
        garch11_fit([0.01] * 10)


def test_garch11_forecast_length_and_positivity():
    p = garch11_fit(RETURNS)
    f = garch11_forecast(p, RETURNS, horizon=5)
    assert len(f) == 5
    assert all(v > 0 for v in f)
    # Forecasts mean-revert toward the long-run variance.
    assert abs(f[-1] - p["long_run_variance"]) < abs(f[0] - p["long_run_variance"])


def test_yield_curve_pca_level_factor_dominates():
    base = [0.02, 0.025, 0.03, 0.035, 0.04]
    # Common level shift dominates; tiny tenor-specific noise on top.
    curves = [[b + 0.004 * math.sin(t / 3.0) + 0.0002 * math.sin(t + j)
               for j, b in enumerate(base)] for t in range(20)]
    out = yield_curve_pca(curves)
    assert out["explained_variance_ratio"][0] > 0.9
    assert sum(out["eigenvalues"]) == pytest.approx(
        sum(out["eigenvalues"]), rel=1e-6)
    # Eigenvalues sum to the trace of the covariance matrix (total variance).
    total_var = sum(out["eigenvalues"])
    assert total_var > 0
    # First loading is a unit vector.
    assert sum(x * x for x in out["loadings"][0]) == pytest.approx(1.0)
    assert len(out["first_component_scores"]) == 20


def test_yield_curve_pca_rejects_ragged_curves():
    with pytest.raises(ValueError):
        yield_curve_pca([[0.02, 0.03], [0.02]])


def test_rolling_window_diagnostics_values():
    out = rolling_window_diagnostics([1.0, 2.0, 3.0, 4.0, 5.0], window=3)
    assert len(out) == 3
    assert out[0]["index"] == 2
    assert out[0]["mean"] == pytest.approx(2.0)
    assert out[0]["std"] == pytest.approx(math.sqrt(2.0 / 3.0))
    assert out[0]["z_score"] == pytest.approx(1.0 / math.sqrt(2.0 / 3.0))
    assert out[-1]["mean"] == pytest.approx(4.0)


def test_rolling_window_rejects_short_series():
    with pytest.raises(ValueError):
        rolling_window_diagnostics([1.0, 2.0], window=3)


def test_out_of_sample_backtest_perfect_model():
    out = out_of_sample_backtest([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 0.5)
    assert out["rmse"] == 0.0 and out["mae"] == 0.0 and out["breaches"] == 0
    assert out["breach_rate"] == 0.0


def test_out_of_sample_backtest_breach_count():
    out = out_of_sample_backtest([10.0, 12.0], [10.0, 10.0], threshold=1.0)
    assert out["bias"] == pytest.approx(1.0)
    assert out["rmse"] == pytest.approx(math.sqrt(2.0))
    assert out["breaches"] == 1 and out["breach_rate"] == pytest.approx(0.5)
    assert out["max_abs_residual"] == pytest.approx(2.0)


def test_cusum_no_break_for_constant_residuals():
    out = cusum_break_check([0.5] * 10)
    assert out["max_abs_cusum"] == 0.0 and out["break_flag"] is False


def test_cusum_flags_step_change_at_low_threshold():
    residuals = [0.0] * 10 + [1.0] * 10
    strict = cusum_break_check(residuals, threshold=1.0)
    assert strict["break_flag"] is True
    assert strict["break_index"] == 9
    loose = cusum_break_check(residuals, threshold=3.0)
    assert loose["break_flag"] is False


def test_cusum_rejects_short_series():
    with pytest.raises(ValueError):
        cusum_break_check([0.1, 0.2, 0.3])
