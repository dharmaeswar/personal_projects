import numpy as np
import pytest

from investment_governance import portfolio


@pytest.fixture
def cov():
    return np.array(
        [[0.04, 0.006, 0.002],
         [0.006, 0.09, 0.004],
         [0.002, 0.004, 0.01]]
    )


def test_min_variance_weights_sum_to_one(cov):
    w = portfolio.min_variance_weights(cov)
    assert w.sum() == pytest.approx(1.0)
    assert np.all(w >= 0)


def test_min_variance_beats_equal_weight(cov):
    w = portfolio.min_variance_weights(cov)
    w_eq = np.full(3, 1 / 3)
    assert portfolio.portfolio_volatility(w, cov) < portfolio.portfolio_volatility(w_eq, cov)


def test_min_variance_respects_cap(cov):
    w = portfolio.min_variance_weights(cov, cap=0.4)
    assert np.all(w <= 0.4 + 1e-6)
    assert w.sum() == pytest.approx(1.0)


def test_cap_too_small_raises(cov):
    with pytest.raises(ValueError):
        portfolio.min_variance_weights(cov, cap=0.2)


def test_portfolio_volatility_equal_weight(cov):
    w = np.full(3, 1 / 3)
    vol = portfolio.portfolio_volatility(w, cov)
    assert vol == pytest.approx(float(np.sqrt(w @ cov @ w)))


def test_sharpe_ratio(cov):
    w = np.array([0.5, 0.3, 0.2])
    mu = np.array([0.08, 0.06, 0.03])
    sr = portfolio.sharpe_ratio(w, mu, cov)
    assert sr == pytest.approx((w @ mu) / portfolio.portfolio_volatility(w, cov))


def test_herfindahl_bounds():
    assert portfolio.herfindahl([1.0, 0.0, 0.0]) == pytest.approx(1.0)
    assert portfolio.herfindahl([1 / 3, 1 / 3, 1 / 3]) == pytest.approx(1 / 3)


def test_turnover():
    assert portfolio.turnover([0.6, 0.4], [0.5, 0.5]) == pytest.approx(0.1)


def test_validate_portfolio_passes_for_min_variance(cov):
    mu = np.array([0.08, 0.06, 0.03])
    w = portfolio.min_variance_weights(cov, cap=0.5)
    checks = portfolio.validate_portfolio(w, cov, mu, cap=0.5)
    assert checks["passed"] is True
    assert checks["weights_sum_to_one"] is True
    assert checks["long_only"] is True


def test_validate_portfolio_fails_for_concentrated():
    cov = np.eye(3) * 0.04
    mu = np.array([0.08, 0.06, 0.03])
    checks = portfolio.validate_portfolio([1.0, 0.0, 0.0], cov, mu)
    assert checks["concentration_below_0.5"] is False
    assert checks["passed"] is False
