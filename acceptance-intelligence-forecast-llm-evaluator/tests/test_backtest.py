import pytest

from acceptance_eval import (
    generate_series, walk_forward, seasonal_naive, holt,
    trend_seasonal_forecast,
)
from acceptance_eval.series import to_values


def _values():
    return to_values(generate_series(n_days=365, seed=7))


def test_walk_forward_fold_count_and_keys():
    res = walk_forward(_values(), lambda h: seasonal_naive(h, 7),
                        horizon=7, folds=6, step=7)
    assert len(res["folds"]) == 6
    assert res["folds"][0]["fold"] == 1
    for f in res["folds"]:
        assert f["mae"] >= 0 and f["rmse"] >= f["mae"]
        assert f["mape"] >= 0
    assert res["mean_mae"] > 0
    assert res["worst_mae"] >= res["mean_mae"]


def test_walk_forward_all_three_models_run():
    vals = _values()
    for fn in (lambda h: seasonal_naive(h, 7),
               lambda h: holt(h, 7),
               lambda h: trend_seasonal_forecast(h, 7)):
        res = walk_forward(vals, fn, horizon=7, folds=6, step=7)
        assert res["mean_mae"] < 0.05  # sane error on a smooth synthetic series


def test_trend_seasonal_beats_naive_on_trended_series():
    vals = _values()
    naive = walk_forward(vals, lambda h: seasonal_naive(h, 7),
                         horizon=7, folds=6, step=7)
    trend = walk_forward(vals, lambda h: trend_seasonal_forecast(h, 7),
                         horizon=7, folds=6, step=7)
    assert trend["mean_mae"] < naive["mean_mae"]


def test_walk_forward_rejects_short_series():
    with pytest.raises(ValueError):
        walk_forward([0.8] * 20, lambda h: seasonal_naive(h, 7),
                     horizon=7, folds=6, step=7)


def test_walk_forward_rejects_wrong_horizon_output():
    with pytest.raises(ValueError):
        walk_forward(_values(), lambda h: [0.9] * 3,
                     horizon=7, folds=2, step=7)
