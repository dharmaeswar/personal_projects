import numpy as np
import pandas as pd

from sys_signal_research.swaps import (
    combine_swap_signals,
    curve_slope,
    generate_swap_curve,
    swap_carry_signal,
    swap_rate_momentum,
    swap_strategy_returns,
    swaps_report,
)


def test_curve_is_seeded_and_reproducible():
    a = generate_swap_curve()
    b = generate_swap_curve()
    pd.testing.assert_frame_equal(a, b)
    c = generate_swap_curve(seed=99)
    assert not a.equals(c)


def test_curve_shape_and_sane_rates():
    curve = generate_swap_curve()
    assert list(curve.columns) == ["2Y", "5Y", "10Y"]
    assert curve.notna().all().all()
    assert curve.min().min() > 1.0
    assert curve.max().max() < 8.0
    # On average the curve slopes up: 10y above 2y.
    assert curve["10Y"].mean() > curve["2Y"].mean()


def test_slope_is_10y_minus_2y_in_bps():
    curve = generate_swap_curve()
    slope = curve_slope(curve)
    expected = (curve["10Y"] - curve["2Y"]) * 100.0
    pd.testing.assert_series_equal(slope, expected, check_names=False)


def test_carry_signal_bounded_and_follows_slope():
    curve = generate_swap_curve()
    sig = swap_carry_signal(curve)
    assert sig.between(-1, 1).all()
    assert sig.notna().all()
    # Steep curve -> positive (receive-fixed) position.
    steep = pd.DataFrame({"2Y": [3.0] * 10, "5Y": [3.5] * 10, "10Y": [5.0] * 10},
                         index=pd.bdate_range("2024-01-01", periods=10))
    assert (swap_carry_signal(steep) == 1.0).all()
    # Inverted curve -> negative (pay-fixed) position.
    inverted = pd.DataFrame({"2Y": [5.0] * 10, "5Y": [4.5] * 10, "10Y": [3.0] * 10},
                            index=pd.bdate_range("2024-01-01", periods=10))
    assert (swap_carry_signal(inverted) == -1.0).all()


def test_momentum_signal_bounded_and_zero_until_lookback():
    curve = generate_swap_curve()
    sig = swap_rate_momentum(curve, lookback=63)
    assert sig.between(-1, 1).all()
    assert sig.notna().all()
    assert sig.iloc[:63].eq(0.0).all()


def test_momentum_is_long_when_rates_fall():
    idx = pd.bdate_range("2024-01-01", periods=200)
    falling = pd.DataFrame(
        {"2Y": 3.5, "5Y": 3.8, "10Y": np.linspace(5.0, 3.0, 200)}, index=idx
    )
    sig = swap_rate_momentum(falling, lookback=63)
    assert sig.iloc[-1] > 0.5
    rising = pd.DataFrame(
        {"2Y": 3.5, "5Y": 3.8, "10Y": np.linspace(3.0, 5.0, 200)}, index=idx
    )
    assert swap_rate_momentum(rising, lookback=63).iloc[-1] < -0.5


def test_strategy_returns_gain_when_rates_fall_for_receive_fixed():
    idx = pd.bdate_range("2024-01-01", periods=100)
    curve = pd.DataFrame(
        {"2Y": 3.5, "5Y": 3.8, "10Y": np.linspace(4.5, 3.5, 100)}, index=idx
    )
    positions = pd.Series(1.0, index=idx)
    result = swap_strategy_returns(curve, positions)
    # Falling rates + positive slope: every applied day should be positive.
    assert (result["return"].iloc[2:] > 0).all()
    assert result["equity"].iloc[-1] > 1.0


def test_carry_accrual_is_positive_with_positive_slope_and_no_rate_move():
    idx = pd.bdate_range("2024-01-01", periods=50)
    curve = pd.DataFrame({"2Y": 3.0, "5Y": 3.5, "10Y": 4.0}, index=idx)
    positions = pd.Series(1.0, index=idx)
    result = swap_strategy_returns(curve, positions)
    # No rate move: return is carry only, 100 bps / 252 per day.
    expected = 100.0 / 10_000.0 / 252.0
    assert np.allclose(result["carry_accrual"].iloc[2:], expected)
    assert np.allclose(result["duration_pnl"].iloc[2:], 0.0)


def test_positions_apply_with_one_day_lag():
    idx = pd.bdate_range("2024-01-01", periods=10)
    curve = pd.DataFrame({"2Y": 3.0, "5Y": 3.5, "10Y": 4.0}, index=idx)
    positions = pd.Series([0.0] * 5 + [1.0] * 5, index=idx)
    result = swap_strategy_returns(curve, positions)
    assert result["position"].iloc[5] == 0.0  # position set at t applies at t+1
    assert result["position"].iloc[6] == 1.0


def test_combined_signal_bounded():
    curve = generate_swap_curve()
    sig = combine_swap_signals(curve)
    assert sig.between(-1, 1).all()
    assert sig.notna().all()


def test_swaps_report_is_complete_and_finite():
    curve = generate_swap_curve()
    report = swaps_report(curve)
    for key in ("mean_slope_bps", "mean_10y_rate", "mean_position",
                "sharpe", "cagr", "annual_vol", "max_drawdown",
                "mean_daily_carry_bps"):
        assert key in report
        assert np.isfinite(report[key])
    assert report["mean_slope_bps"] > 0  # upward-sloping curve on average
    assert report["max_drawdown"] <= 0
