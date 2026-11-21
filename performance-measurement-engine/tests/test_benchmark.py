"""Golden-value regression tests for benchmark-relative returns."""

import pytest

from perf.benchmark import benchmark_relative, excess_series, proxy_fill


def test_arithmetic_excess():
    assert benchmark_relative(0.10, 0.06, geometric=False) == pytest.approx(0.04)


def test_geometric_excess():
    assert benchmark_relative(0.10, 0.06) == pytest.approx(0.04 / 1.06, rel=1e-12)


def test_proxy_fill_marks_filled_periods():
    filled = proxy_fill([0.05, 0.06], [0.04, None], [0.03, 0.07])
    assert filled == [(0.04, False), (0.07, True)]


def test_proxy_fill_rejects_missing_proxy():
    with pytest.raises(ValueError):
        proxy_fill([0.05], [None], [None])


def test_proxy_fill_rejects_misaligned_series():
    with pytest.raises(ValueError):
        proxy_fill([0.05, 0.06], [0.04], [0.03, 0.07])


def test_excess_series_with_proxy_fill():
    # Geometric excess by default: 1.05/1.04 - 1 and 1.06/1.07 - 1.
    series = excess_series([0.05, 0.06], [0.04, None], [0.03, 0.07])
    assert series[0]["excess"] == pytest.approx(0.01 / 1.04, rel=1e-12)
    assert series[0]["filled"] is False
    # Period 2: portfolio 0.06 vs proxy-filled benchmark 0.07.
    assert series[1]["benchmark"] == pytest.approx(0.07)
    assert series[1]["filled"] is True
    assert series[1]["excess"] == pytest.approx(-0.01 / 1.07, rel=1e-12)
