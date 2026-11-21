"""Golden-value regression tests for GIPS-adjacent composite returns."""

import pytest

from perf.composite import (asset_weighted_return, composite_dispersion,
                            composite_summary, equal_weighted_return)


def test_asset_weighted_return_hand_computed():
    # (1000 * 0.10 + 3000 * 0.05) / 4000 = 250 / 4000 = 0.0625.
    assert asset_weighted_return([(1000.0, 0.10), (3000.0, 0.05)]) == \
        pytest.approx(0.0625)


def test_asset_weighted_ignores_zero_value_portfolio():
    assert asset_weighted_return([(0.0, 0.99), (1000.0, 0.08)]) == \
        pytest.approx(0.08)


def test_asset_weighted_rejects_negative_value():
    with pytest.raises(ValueError):
        asset_weighted_return([(-100.0, 0.05)])


def test_asset_weighted_rejects_empty_composite():
    with pytest.raises(ValueError):
        asset_weighted_return([])


def test_equal_weighted_return():
    assert equal_weighted_return([0.10, 0.05]) == pytest.approx(0.075)


def test_composite_dispersion_hand_computed():
    # Returns 0.10 and 0.05, mean 0.075, deviations +/-0.025, so the
    # population standard deviation is 0.025.
    assert composite_dispersion([0.10, 0.05]) == pytest.approx(0.025)


def test_composite_dispersion_single_portfolio_is_zero():
    assert composite_dispersion([0.07]) == pytest.approx(0.0)


def test_composite_summary():
    summary = composite_summary([(1000.0, 0.10), (3000.0, 0.05),
                                 (2000.0, 0.08)])
    # Asset-weighted: (100 + 150 + 160) / 6000 = 410 / 6000.
    assert summary["asset_weighted_return"] == pytest.approx(410.0 / 6000.0)
    # Equal-weighted: (0.10 + 0.05 + 0.08) / 3.
    assert summary["equal_weighted_return"] == pytest.approx(0.23 / 3.0)
    assert summary["portfolio_count"] == 3
    assert summary["total_beginning_value"] == pytest.approx(6000.0)
    assert summary["dispersion"] > 0
