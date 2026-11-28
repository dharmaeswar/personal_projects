import os

from options.data import (simulate_underlying, build_chain, write_chain_csv,
                          read_chain_csv, write_prices_json, read_prices_json)


def test_underlying_deterministic_and_positive():
    a = simulate_underlying(seed=7)
    b = simulate_underlying(seed=7)
    assert a == b
    assert len(a) == 253  # start + 252 days
    assert all(p > 0 for p in a)
    assert a[0] == 100.0


def test_chain_shape_and_spread():
    chain = build_chain(100.0)
    assert len(chain) == 42  # 3 expiries x 7 strikes x 2 kinds
    for q in chain:
        assert q["bid"] <= q["mid"] <= q["ask"]
        assert q["bid"] > 0


def test_chain_csv_round_trip(tmp_path):
    chain = build_chain(100.0)
    path = str(tmp_path / "chain.csv")
    write_chain_csv(chain, path)
    back = read_chain_csv(path)
    assert len(back) == len(chain)
    assert back[0]["mid"] == chain[0]["mid"]
    assert back[0]["expiry_days"] == chain[0]["expiry_days"]
    assert isinstance(back[0]["strike"], float)


def test_prices_json_round_trip(tmp_path):
    prices = simulate_underlying(seed=3)
    path = str(tmp_path / "prices.json")
    write_prices_json(prices, path)
    assert read_prices_json(path) == prices
