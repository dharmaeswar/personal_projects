import math

import pytest

from muni_engine import (
    MunicipalBond, TaxExemptCurve, bootstrap_curve, dv01,
    duration_convexity, key_rate_durations, option_adjusted_spread,
    callable_bond_price, price, spread_scenarios, yield_to_maturity,
    yield_to_call, yield_to_worst, RelativeValueScreen,
)


@pytest.fixture
def curve():
    return TaxExemptCurve([1, 2, 5, 10, 20, 30],
                          [0.022, 0.025, 0.029, 0.035, 0.041, 0.044])


@pytest.fixture
def bond():
    return MunicipalBond(coupon=0.05, maturity_years=20,
                         call_dates=[10.0], call_prices=[100.0])


@pytest.fixture
def bullet():
    return MunicipalBond(coupon=0.04, maturity_years=10)


# --- curve ---

def test_zero_rate_interpolates_and_extrapolates_flat(curve):
    assert curve.zero_rate(5) == pytest.approx(0.029)
    assert 0.029 < curve.zero_rate(7.5) < 0.035
    assert curve.zero_rate(0.5) == pytest.approx(0.022)
    assert curve.zero_rate(40) == pytest.approx(0.044)


def test_discount_factor_matches_zero_rate(curve):
    assert curve.discount_factor(10) == pytest.approx(1 / 1.035 ** 10)


def test_taxable_equivalent_yield():
    assert TaxExemptCurve.taxable_equivalent_yield(0.03, 0.37) == pytest.approx(0.047619, rel=1e-4)
    with pytest.raises(ValueError):
        TaxExemptCurve.taxable_equivalent_yield(0.03, 1.0)


def test_bootstrap_reprices_par_bonds():
    par_tenors = [1, 2, 3, 5, 7, 10, 20, 30]
    par_yields = [0.022, 0.024, 0.026, 0.029, 0.032, 0.035, 0.041, 0.044]
    boot = bootstrap_curve(par_tenors, par_yields)
    for tenor, y in zip(par_tenors, par_yields):
        b = MunicipalBond(coupon=y, maturity_years=tenor)
        priced = sum(cf * boot.discount_factor(t) for t, cf in b.cashflows())
        assert priced == pytest.approx(100.0, abs=1.0)


def test_bootstrap_rejects_bad_inputs():
    with pytest.raises(ValueError):
        bootstrap_curve([1, 2], [0.02])
    with pytest.raises(ValueError):
        TaxExemptCurve([2, 1], [0.02, 0.03])


# --- pricing / yields ---

def test_par_bond_prices_at_100(bullet):
    assert price(bullet, 0.04) == pytest.approx(100.0, abs=1e-6)


def test_price_falls_as_yield_rises(bullet):
    assert price(bullet, 0.03) > 100.0 > price(bullet, 0.05)


def test_ytm_round_trips_price(bullet):
    ytm = yield_to_maturity(bullet, 96.25)
    assert price(bullet, ytm) == pytest.approx(96.25, abs=1e-6)


def test_yield_to_call_below_ytm_for_premium_callable(bond):
    # Premium callable bond: yield-to-call is the binding (lower) yield.
    ytc = yield_to_call(bond, 104.50, 0)
    ytm = yield_to_maturity(bond, 104.50)
    assert ytc < ytm


def test_yield_to_worst_picks_call_for_premium_bond(bond):
    ytw, source = yield_to_worst(bond, 104.50)
    assert source == "call@10.0y"
    assert ytw == pytest.approx(yield_to_call(bond, 104.50, 0))


def test_yield_to_worst_picks_maturity_for_discount_bond(bond):
    ytw, source = yield_to_worst(bond, 92.00)
    assert source == "maturity"


def test_bond_validation():
    with pytest.raises(ValueError):
        MunicipalBond(coupon=0.05, maturity_years=10,
                      call_dates=[5.0], call_prices=[100.0, 100.0])
    with pytest.raises(ValueError):
        MunicipalBond(coupon=0.05, maturity_years=10,
                      call_dates=[10.0], call_prices=[100.0])


# --- OAS ---

def test_callable_worth_less_than_bullet(curve, bond):
    bullet = MunicipalBond(coupon=0.05, maturity_years=20)
    assert callable_bond_price(bond, curve, 0.0) < callable_bond_price(bullet, curve, 0.0)


def test_oas_reprices_market_price(curve, bond):
    oas = option_adjusted_spread(bond, curve, 104.50, vol=0.10)
    assert callable_bond_price(bond, curve, oas) == pytest.approx(104.50, abs=0.05)


def test_oas_rises_when_market_price_falls(curve, bond):
    cheap = option_adjusted_spread(bond, curve, 100.00, vol=0.10)
    rich = option_adjusted_spread(bond, curve, 104.50, vol=0.10)
    assert cheap > rich


# --- risk ---

def test_duration_convexity_sane(bullet):
    duration, convexity = duration_convexity(bullet, 0.04)
    assert 7.0 < duration < 9.0  # 10y 4% bond modified duration
    assert convexity > 0


def test_dv01_positive_and_small(bullet):
    d = dv01(bullet, 0.04)
    assert 0.05 < d < 0.15  # ~$0.08 per 100 par per bp for a 10y bond


def test_key_rate_durations_sum_near_total_duration(curve, bullet):
    krds = key_rate_durations(bullet, curve)
    assert set(krds) == {2, 5, 10, 20, 30}
    total = sum(krds.values())
    duration, _ = duration_convexity(bullet, 0.04)
    assert total == pytest.approx(duration, rel=0.35)


def test_spread_scenarios_monotone(bullet):
    scenarios = spread_scenarios(bullet, 0.04)
    assert scenarios[-100] > 0 > scenarios[100]
    assert scenarios[-100] > scenarios[-50] > scenarios[50] > scenarios[100]


# --- relative value ---

def _universe():
    return [
        {"id": "A", "maturity_years": 5, "coupon": 0.03, "rating": "AAA",
         "callable": False, "spread_bp": 28},
        {"id": "B", "maturity_years": 10, "coupon": 0.04, "rating": "AA",
         "callable": True, "spread_bp": 52},
        {"id": "C", "maturity_years": 20, "coupon": 0.05, "rating": "AA",
         "callable": True, "spread_bp": 71},
        {"id": "D", "maturity_years": 30, "coupon": 0.045, "rating": "A",
         "callable": True, "spread_bp": 88},
        {"id": "E", "maturity_years": 7, "coupon": 0.035, "rating": "AAA",
         "callable": False, "spread_bp": 31},
        {"id": "F", "maturity_years": 12, "coupon": 0.05, "rating": "A",
         "callable": True, "spread_bp": 64},
        {"id": "G", "maturity_years": 15, "coupon": 0.04, "rating": "AA",
         "callable": False, "spread_bp": 49},
        {"id": "H", "maturity_years": 25, "coupon": 0.05, "rating": "BBB",
         "callable": True, "spread_bp": 118},
    ]


def test_screen_fits_and_flags():
    screen = RelativeValueScreen()
    coef = screen.fit(_universe())
    assert coef["maturity_years"] > 0  # longer bonds carry wider spreads
    assert 0.0 < screen.r_squared(_universe()) < 1.0
    flagged = screen.screen(_universe())
    assert all(r["flag"] in ("CHEAP", "RICH", "FAIR") for r in flagged)
    assert len(flagged) == 8


def test_screen_flags_an_outlier_as_cheap():
    universe = _universe()
    universe.append({"id": "OUT", "maturity_years": 10, "coupon": 0.04,
                     "rating": "AA", "callable": True, "spread_bp": 150})
    screen = RelativeValueScreen()
    screen.fit(universe)
    flagged = {r["id"]: r for r in screen.screen(universe)}
    assert flagged["OUT"]["flag"] == "CHEAP"
    assert flagged["OUT"]["residual_bp"] > 25


def test_screen_needs_enough_bonds():
    screen = RelativeValueScreen()
    with pytest.raises(ValueError):
        screen.fit(_universe()[:3])


def test_predict_before_fit_raises():
    with pytest.raises(ValueError):
        RelativeValueScreen().predict(_universe()[0])
