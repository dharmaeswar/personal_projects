import numpy as np
import pytest

from investment_governance import allocation


@pytest.fixture
def cov():
    return np.array(
        [[0.04, 0.006, 0.002],
         [0.006, 0.09, 0.004],
         [0.002, 0.004, 0.01]]
    )


def test_risk_parity_weights_sum_to_one(cov):
    w = allocation.risk_parity_weights(cov)
    assert w.sum() == pytest.approx(1.0)
    assert np.all(w >= 0)


def test_risk_parity_equal_contributions(cov):
    w = allocation.risk_parity_weights(cov)
    rc = allocation.risk_contributions(w, cov)
    assert np.allclose(rc, 1.0 / 3, atol=0.01)


def test_risk_contributions_sum_to_one(cov):
    rc = allocation.risk_contributions([0.5, 0.3, 0.2], cov)
    assert rc.sum() == pytest.approx(1.0)


def test_risk_parity_prefers_low_vol_asset(cov):
    # Asset 3 has the lowest variance, so it should get the largest weight.
    w = allocation.risk_parity_weights(cov)
    assert w[2] > w[1]


def test_diversification_ratio_above_one(cov):
    w = np.full(3, 1 / 3)
    vols = np.sqrt(np.diag(cov))
    assert allocation.diversification_ratio(w, vols, cov) > 1.0


def test_diversification_ratio_single_asset(cov):
    vols = np.sqrt(np.diag(cov))
    assert allocation.diversification_ratio([1.0, 0.0, 0.0], vols, cov) == pytest.approx(1.0)


def test_max_drawdown_no_fall():
    assert allocation.max_drawdown([1.0, 1.1, 1.2]) == pytest.approx(0.0)


def test_max_drawdown_known():
    # Peak 1.2, trough 0.9 -> 25% drawdown.
    assert allocation.max_drawdown([1.0, 1.2, 0.9, 1.0]) == pytest.approx(0.25)


def test_max_drawdown_empty():
    assert allocation.max_drawdown([]) == 0.0
