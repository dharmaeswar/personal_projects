import numpy as np
import pytest

from exp_platform.commercial import (
    CHANNELS,
    channel_attribution,
    commercial_measurement_report,
    generate_commercial_panel,
    geo_holdout_estimate,
)


def _territory_means(panel):
    territory = panel["territory"]
    treated = panel["treated"]
    ids = np.unique(territory)
    pre, post, is_t = [], [], []
    for t in ids:
        mask = territory == t
        pre.append(panel["pre_trx"][mask].mean())
        post.append(panel["post_trx"][mask].mean())
        is_t.append(bool(treated[mask][0]))
    return np.array(pre), np.array(post), np.array(is_t)


def test_geo_holdout_recovers_true_lift():
    panel = generate_commercial_panel(true_lift=12.0)
    pre, post, is_t = _territory_means(panel)
    out = geo_holdout_estimate(pre[is_t], post[is_t], pre[~is_t], post[~is_t])
    assert abs(out["estimate"] - 12.0) < 2.0
    assert out["p_value"] < 0.01
    assert out["n_treated_territories"] == 20
    assert abs(out["total_incremental"] - out["estimate"] * 20) < 1e-9


def test_geo_holdout_zero_lift_not_significant():
    panel = generate_commercial_panel(true_lift=0.0)
    pre, post, is_t = _territory_means(panel)
    out = geo_holdout_estimate(pre[is_t], post[is_t], pre[~is_t], post[~is_t])
    assert abs(out["estimate"]) < 2.0
    assert out["p_value"] > 0.05


def test_attribution_recovers_channel_effects_and_shares_sum_to_one():
    panel = generate_commercial_panel()
    out = channel_attribution(
        {c: panel[c] for c in CHANNELS}, panel["post_trx_attribution"],
        baseline=panel["pre_trx"])
    true = panel["true_channel_effects"]
    for c in CHANNELS:
        assert abs(out["channel_coefficients"][c] - true[c]) < 0.25
    assert abs(sum(out["channel_shares"].values()) - 1.0) < 1e-9
    # Rep visits have the largest true effect and the most touches, so
    # they must carry the largest share.
    assert out["channel_shares"]["rep_visits"] == max(
        out["channel_shares"].values())
    assert out["r_squared"] > 0.5


def test_attribution_no_touches_raises():
    zeros = {c: np.zeros(50, dtype=int) for c in CHANNELS}
    with pytest.raises(ValueError):
        channel_attribution(zeros, np.ones(50))


def test_attribution_mismatched_lengths_raises():
    touches = {c: np.ones(10) for c in CHANNELS}
    with pytest.raises(ValueError):
        channel_attribution(touches, np.ones(9))


def test_commercial_report_end_to_end():
    panel = generate_commercial_panel(true_lift=12.0)
    rep = commercial_measurement_report(panel)
    assert rep["n_territories"] == 40
    assert rep["n_treated_territories"] == 20
    assert abs(rep["geo_holdout"]["estimate"] - 12.0) < 2.0
    assert abs(sum(rep["attribution"]["channel_shares"].values()) - 1.0) < 1e-9
    assert rep["attribution"]["channel_shares"]["rep_visits"] > 0.4
