import numpy as np
import pytest

from investment_governance import risk


def test_historical_var_matches_quantile():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, size=1000)
    assert risk.historical_var(r, 0.05) == pytest.approx(-np.quantile(r, 0.05))


def test_historical_var_positive_for_losses():
    r = np.array([-0.05, -0.02, 0.01, 0.02, -0.01] * 20, dtype=float)
    assert risk.historical_var(r, 0.05) > 0


def test_historical_var_bad_alpha():
    with pytest.raises(ValueError):
        risk.historical_var([0.01, -0.01], alpha=1.5)


def test_expected_shortfall_exceeds_var():
    rng = np.random.default_rng(2)
    r = rng.normal(0, 0.01, size=2000)
    assert risk.expected_shortfall(r, 0.05) >= risk.historical_var(r, 0.05)


def test_count_exceptions():
    returns = np.array([-0.06, -0.01, 0.02, -0.04])
    var = np.array([0.05, 0.05, 0.05, 0.05])
    assert list(risk.count_exceptions(returns, var)) == [1, 0, 0, 0]


def test_count_exceptions_shape_mismatch():
    with pytest.raises(ValueError):
        risk.count_exceptions([0.01, -0.02], [0.05])


def test_kupiec_does_not_reject_correct_model():
    rng = np.random.default_rng(5)
    exc = (rng.random(1000) < 0.05).astype(int)
    stat, reject = risk.kupiec_pof(exc, 0.05)
    assert reject is False
    assert stat < 3.841


def test_kupiec_rejects_badly_wrong_model():
    exc = np.ones(200, dtype=int)  # breach every day at 95% VaR
    stat, reject = risk.kupiec_pof(exc, 0.05)
    assert reject is True
    assert stat > 3.841


def test_kupiec_zero_exceptions():
    stat, reject = risk.kupiec_pof(np.zeros(250, dtype=int), 0.05)
    assert reject is True  # far too few breaches is also a failure


def test_christoffersen_no_reject_for_independent():
    rng = np.random.default_rng(9)
    exc = (rng.random(1000) < 0.05).astype(int)
    stat, reject = risk.christoffersen_independence(exc)
    assert reject is False


def test_christoffersen_rejects_clustered_breaches():
    exc = np.zeros(500, dtype=int)
    exc[100:120] = 1  # one 20-day breach cluster
    stat, reject = risk.christoffersen_independence(exc)
    assert reject is True


def test_backtest_var_summary():
    rng = np.random.default_rng(11)
    r = rng.normal(0, 0.01, size=500)
    var = np.full(500, risk.historical_var(r, 0.05))
    out = risk.backtest_var(r, var, alpha=0.05)
    assert out["n_observations"] == 500
    assert out["expected_exceptions"] == 25.0
    assert out["exceptions"] == int(np.sum(r < -var))
    assert out["passed"] is True
