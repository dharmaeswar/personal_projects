import numpy as np
import pandas as pd

from sys_signal_research.backtest import backtest
from sys_signal_research.data import generate_prices
from sys_signal_research.portfolio import build_portfolio
from sys_signal_research.signals import moving_average_crossover, time_series_momentum

PRICES = generate_prices()


def _results():
    return {
        "ES": backtest(PRICES["ES"], time_series_momentum(PRICES["ES"]), cost_bps=2.0),
        "GC": backtest(PRICES["GC"], moving_average_crossover(PRICES["GC"]), cost_bps=2.0),
    }


def test_build_portfolio_weights_sum_to_one():
    port_rets, weights = build_portfolio(_results())
    assert abs(weights.sum() - 1.0) < 1e-9
    assert (weights >= 0).all()
    assert len(port_rets) == len(PRICES)
    assert port_rets.notna().all()


def test_build_portfolio_matches_explicit_weights():
    results = _results()
    port_rets, weights = build_portfolio(results, weights={"ES": 0.75, "GC": 0.25})
    expected = 0.75 * results["ES"]["return"] + 0.25 * results["GC"]["return"]
    pd.testing.assert_series_equal(port_rets, expected, check_names=False)
    assert list(weights) == [0.75, 0.25]


def test_build_portfolio_normalises_weights():
    _, weights = build_portfolio(_results(), weights={"ES": 3.0, "GC": 1.0})
    assert abs(weights["ES"] - 0.75) < 1e-9
    assert abs(weights["GC"] - 0.25) < 1e-9
