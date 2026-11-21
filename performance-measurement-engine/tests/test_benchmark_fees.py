import pytest

from perf.benchmark import benchmark_relative, proxy_fill, excess_series
from perf.fees import FeeTerms, gross_to_net


def test_benchmark_relative_geometric():
    assert abs(benchmark_relative(0.12, 0.10) - (1.12 / 1.10 - 1.0)) < 1e-12


def test_benchmark_relative_arithmetic():
    assert abs(benchmark_relative(0.12, 0.10, geometric=False) - 0.02) < 1e-12


def test_proxy_fill_marks_filled_periods():
    filled = proxy_fill([0.12, 0.08, 0.10], [0.10, None, 0.08],
                        [0.09, 0.07, 0.06])
    assert filled == [(0.10, False), (0.07, True), (0.08, False)]


def test_proxy_fill_requires_proxy_when_benchmark_missing():
    with pytest.raises(ValueError):
        proxy_fill([0.12], [None], [None])


def test_proxy_fill_rejects_misaligned_series():
    with pytest.raises(ValueError):
        proxy_fill([0.12, 0.08], [0.10], [0.09, 0.07])


def test_excess_series_with_proxy_fill():
    series = excess_series([0.12, 0.08, 0.10], [0.10, None, 0.08],
                           proxy_returns=[0.09, 0.07, 0.06])
    assert series[0]["filled"] is False
    assert series[1]["filled"] is True
    assert abs(series[1]["excess"] - (1.08 / 1.07 - 1.0)) < 1e-12
    assert abs(series[2]["excess"] - (1.10 / 1.08 - 1.0)) < 1e-12


def test_gross_to_net_bridge():
    # NAV 1000, gross gain 100 (10%); fee 1% of NAV = 10; hurdle 8% -> 80;
    # carry 20% of (100 - 80) = 4; net gain 86, net return 8.6%.
    bridge = gross_to_net(1000.0, 100.0,
                          FeeTerms(management_fee_rate=0.01, carry_rate=0.20,
                                   hurdle_rate=0.08))
    assert bridge["management_fee"] == 10.0
    assert bridge["carry"] == 4.0
    assert bridge["net_gain"] == 86.0
    assert abs(bridge["net_return"] - 0.086) < 1e-12
    assert bridge["residual"] == 0.0


def test_gross_to_net_no_carry_below_hurdle():
    bridge = gross_to_net(1000.0, 50.0,
                          FeeTerms(management_fee_rate=0.01, carry_rate=0.20,
                                   hurdle_rate=0.08))
    assert bridge["carry"] == 0.0
    assert bridge["net_gain"] == 40.0
