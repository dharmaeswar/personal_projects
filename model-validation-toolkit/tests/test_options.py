import math
import pytest
from model_validation_toolkit.options import (
    black_scholes_price,
    greeks,
    implied_volatility,
    put_call_parity_gap,
    validate_option_book,
)

# Reference values: S=100, K=100, r=0.05, T=1, sigma=0.20.
CALL_100 = 10.4506
PUT_100 = 5.5735


def test_black_scholes_call_known_value():
    price = black_scholes_price(100.0, 100.0, 0.05, 1.0, 0.20, "call")
    assert price == pytest.approx(CALL_100, abs=1e-3)


def test_black_scholes_put_known_value():
    price = black_scholes_price(100.0, 100.0, 0.05, 1.0, 0.20, "put")
    assert price == pytest.approx(PUT_100, abs=1e-3)


def test_put_call_parity_holds_for_model_prices():
    call = black_scholes_price(100.0, 100.0, 0.05, 1.0, 0.20, "call")
    put = black_scholes_price(100.0, 100.0, 0.05, 1.0, 0.20, "put")
    assert put_call_parity_gap(call, put, 100.0, 100.0, 0.05, 1.0) == pytest.approx(0.0, abs=1e-9)


def test_put_call_parity_gap_detects_violation():
    gap = put_call_parity_gap(CALL_100 + 1.0, PUT_100, 100.0, 100.0, 0.05, 1.0)
    assert gap == pytest.approx(1.0, abs=1e-3)


def test_implied_volatility_recovers_sigma():
    iv = implied_volatility(CALL_100, 100.0, 100.0, 0.05, 1.0, "call")
    assert iv == pytest.approx(0.20, abs=1e-4)


def test_implied_volatility_put_recovers_sigma():
    iv = implied_volatility(PUT_100, 100.0, 100.0, 0.05, 1.0, "put")
    assert iv == pytest.approx(0.20, abs=1e-4)


def test_implied_volatility_rejects_below_intrinsic():
    with pytest.raises(ValueError):
        implied_volatility(0.5, 100.0, 90.0, 0.05, 1.0, "call")


def test_greeks_call_delta_and_signs():
    g = greeks(100.0, 100.0, 0.05, 1.0, 0.20, "call")
    assert g["delta"] == pytest.approx(0.6368, abs=1e-3)
    assert g["gamma"] > 0 and g["vega"] > 0 and g["theta"] < 0


def test_greeks_put_delta_negative():
    g = greeks(100.0, 100.0, 0.05, 1.0, 0.20, "put")
    assert g["delta"] == pytest.approx(-0.3632, abs=1e-3)
    assert g["gamma"] > 0 and g["vega"] > 0


def test_black_scholes_rejects_bad_inputs():
    with pytest.raises(ValueError):
        black_scholes_price(0.0, 100.0, 0.05, 1.0, 0.20)
    with pytest.raises(ValueError):
        black_scholes_price(100.0, 100.0, 0.05, 0.0, 0.20)
    with pytest.raises(ValueError):
        black_scholes_price(100.0, 100.0, 0.05, 1.0, 0.20, "straddle")


def test_validate_book_passes_when_marks_match_model():
    book = [
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "call", "market_price": CALL_100},
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "put", "market_price": PUT_100},
    ]
    out = validate_option_book(book)
    assert out["contracts"] == 2 and out["breaches"] == 0 and out["parity_breaches"] == 0


def test_validate_book_flags_mispriced_contract():
    book = [
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "call", "market_price": CALL_100},
        {"spot": 100.0, "strike": 110.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "call", "market_price": 15.0},
    ]
    out = validate_option_book(book)
    assert out["breaches"] == 1
    assert out["worst_index"] == 1
    assert out["worst_relative_error"] > 0.5


def test_validate_book_flags_parity_breach():
    book = [
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "call", "market_price": CALL_100 + 0.5},
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "time_to_expiry": 1.0,
         "vol": 0.20, "option_type": "put", "market_price": PUT_100},
    ]
    out = validate_option_book(book)
    assert out["parity_breaches"] == 2
    assert out["results"][0]["parity_gap"] == pytest.approx(0.5, abs=1e-3)


def test_validate_book_rejects_bad_tolerance():
    with pytest.raises(ValueError):
        validate_option_book([], tolerance=0.0)
