"""Tests for model monitoring (mmm_geo/monitoring.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mmm_geo.data_gen import generate_weekly
from mmm_geo.mmm import fit_mmm
from mmm_geo.monitoring import (
    compare_distributions,
    monitor_mmm,
    monitor_predictions,
    monitoring_summary_lines,
)


def _frame(values, columns=("spend",)):
    return pd.DataFrame({c: np.asarray(v, dtype=float)
                         for c, v in zip(columns, values)})


def test_identical_distributions_are_not_flagged():
    ref = _frame([[10.0, 11.0, 9.0, 10.5, 12.0, 8.5, 10.0, 11.5]])
    rows = compare_distributions(ref, ref.copy(), ["spend"])
    assert len(rows) == 1
    assert rows[0]["flagged"] is False
    assert rows[0]["standardised_shift"] == 0.0


def test_large_mean_shift_is_flagged():
    ref = _frame([[10.0, 11.0, 9.0, 10.5, 12.0, 8.5, 10.0, 11.5]])
    cur = _frame([[30.0, 31.0, 29.0, 30.5, 32.0, 28.5, 30.0, 31.5]])
    rows = compare_distributions(ref, cur, ["spend"])
    assert rows[0]["flagged"] is True
    assert rows[0]["standardised_shift"] > 0.5
    assert rows[0]["p_value"] < 0.05


def test_small_shift_within_noise_is_not_flagged():
    rng = np.random.default_rng(0)
    ref = _frame([rng.normal(100, 5, 200)])
    cur = _frame([rng.normal(100.1, 5, 200)])
    rows = compare_distributions(ref, cur, ["spend"])
    assert rows[0]["flagged"] is False


def test_prediction_check_passes_when_error_matches_holdout():
    res = monitor_predictions([100.0, 200.0, 150.0], [101.0, 198.0, 152.0],
                              holdout_mape=0.01)
    assert res["flagged"] is False
    assert res["mape_ratio"] < 2.0


def test_prediction_check_flags_when_error_doubles():
    res = monitor_predictions([100.0, 200.0, 150.0], [130.0, 260.0, 195.0],
                              holdout_mape=0.01)
    assert res["flagged"] is True
    assert res["mape_ratio"] > 2.0


def test_prediction_check_flags_on_high_absolute_mape():
    res = monitor_predictions([100.0, 200.0], [110.0, 220.0],
                              holdout_mape=0.04)
    # MAPE 10% is above the 5% absolute bar even though the ratio is 2.5x.
    assert res["flagged"] is True


def test_monitor_mmm_on_holdout_weeks_is_ok_or_watch():
    weekly = generate_weekly()
    mmm = fit_mmm(weekly)
    result = monitor_mmm(mmm, weekly.iloc[:-12], weekly.iloc[-12:])
    # The holdout weeks come from the same generator, so prediction error
    # must not have drifted — but the last 12 weeks are a different season
    # (seasonality falls sharply), so distribution flags are expected and
    # the verdict is WATCH, never RETRAIN.
    assert result["verdict"] == "WATCH"
    assert result["predictions"]["flagged"] is False
    assert result["predictions"]["mape_ratio"] == pytest.approx(1.0, abs=0.05)
    assert len(result["distribution"]) == 7  # 5 spend cols + seasonality + sales


def test_monitor_mmm_flags_a_shifted_world():
    weekly = generate_weekly()
    mmm = fit_mmm(weekly)
    shifted = weekly.iloc[-12:].copy()
    # Triple paid-social spend in the "new" weeks: a real distribution shift.
    shifted["spend_paid_social"] = shifted["spend_paid_social"] * 3
    result = monitor_mmm(mmm, weekly.iloc[:-12], shifted)
    flagged = [r for r in result["distribution"] if r["flagged"]]
    assert any(r["column"] == "spend_paid_social" for r in flagged)


def test_summary_lines_state_the_verdict():
    weekly = generate_weekly()
    mmm = fit_mmm(weekly)
    result = monitor_mmm(mmm, weekly.iloc[:-12], weekly.iloc[-12:])
    lines = monitoring_summary_lines(result)
    assert lines[0].startswith(f"Verdict: {result['verdict']}")
    assert any("spend_paid_search" in line for line in lines)
