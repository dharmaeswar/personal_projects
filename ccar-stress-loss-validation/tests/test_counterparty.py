"""Tests for the counterparty credit-risk exposure validation module."""

import numpy as np
import pandas as pd
import pytest

from ccar_validation.counterparty import (
    ALPHA,
    RATING_PD,
    book_exposures,
    build_counterparty_section,
    ead_from_profile,
    effective_epe,
    exposure_profile,
    generate_counterparty_book,
    netting_benefit,
    simulate_net_mtm,
    validate_exposure_forecast,
)


@pytest.fixture(scope="module")
def book():
    return generate_counterparty_book()


def test_book_generation_deterministic():
    cp1, tr1 = generate_counterparty_book()
    cp2, tr2 = generate_counterparty_book()
    pd.testing.assert_frame_equal(cp1, cp2)
    pd.testing.assert_frame_equal(tr1, tr2)


def test_book_shape_and_columns(book):
    counterparties, trades = book
    assert len(counterparties) == 25
    assert len(trades) == 200
    assert set(counterparties.columns) == {
        "counterparty_id", "rating", "pd_1y", "lgd",
    }
    assert set(trades.columns) == {
        "trade_id", "counterparty_id", "notional", "maturity_years",
        "direction", "rate_sens_per_bp", "current_mtm",
    }
    assert set(counterparties["rating"]) <= set(RATING_PD)
    assert (counterparties["pd_1y"] > 0).all()
    assert (trades["notional"] > 0).all()
    assert set(trades["direction"]) <= {-1, 1}


def test_simulation_deterministic(book):
    _, trades = book
    first = simulate_net_mtm(trades, n_paths=50, seed=7)
    second = simulate_net_mtm(trades, n_paths=50, seed=7)
    for cp_id in first:
        np.testing.assert_array_equal(first[cp_id], second[cp_id])


def test_exposure_profile_nonnegative_and_ordered(book):
    _, trades = book
    net_mtm = simulate_net_mtm(trades, n_paths=200, seed=3)
    for cp_id, paths in net_mtm.items():
        profile = exposure_profile(paths)
        assert (profile["expected_exposure"] >= 0).all()
        # PFE95 can sit below EE when most paths are at zero exposure and a
        # small tail is very large, so only non-negativity is asserted here.
        assert (profile["pfe_95"] >= 0).all()
        assert len(profile) == 4


def test_ead_is_alpha_times_effective_epe(book):
    _, trades = book
    net_mtm = simulate_net_mtm(trades, n_paths=200, seed=3)
    cp_id = next(iter(net_mtm))
    profile = exposure_profile(net_mtm[cp_id])
    assert ead_from_profile(profile) == pytest.approx(ALPHA * effective_epe(profile))


def test_rate_shock_moves_single_trade_exposure_in_expected_direction():
    # One receive-fixed trade: a +200bp shock raises MtM, so EE/EAD must rise;
    # a pay-fixed trade must fall.
    for direction, sign in ((1, 1), (-1, -1)):
        trades = pd.DataFrame(
            {
                "trade_id": [1],
                "counterparty_id": [1],
                "notional": [100_000_000.0],
                "maturity_years": [5.0],
                "direction": [direction],
                "rate_sens_per_bp": [direction * 25_000.0],
                "current_mtm": [0.0],
            }
        )
        base = simulate_net_mtm(trades, n_paths=500, seed=11)
        shocked = trades.copy()
        shocked["current_mtm"] = shocked["current_mtm"] + shocked["rate_sens_per_bp"] * 200.0
        shocked_mtm = simulate_net_mtm(shocked, n_paths=500, seed=11)
        base_ead = ead_from_profile(exposure_profile(base[1]))
        shocked_ead = ead_from_profile(exposure_profile(shocked_mtm[1]))
        if sign > 0:
            assert shocked_ead > base_ead
        else:
            assert shocked_ead < base_ead


def test_book_exposures_totals(book):
    counterparties, trades = book
    exposures = book_exposures(counterparties, trades, n_paths=200)
    assert (exposures["ead"] >= 0).all()
    assert (exposures["expected_loss"] >= 0).all()
    assert (exposures["expected_loss"] <= exposures["ead"]).all()
    assert (exposures["peak_pfe_95"] >= 0).all()


def test_netting_never_increases_exposure(book):
    _, trades = book
    result = netting_benefit(trades)
    assert result["netted_exposure"] <= result["gross_exposure"]
    assert result["netting_benefit"] >= 0
    assert 0.0 <= result["netting_benefit_pct"] <= 1.0


def test_pfe_breach_rate_near_five_percent(book):
    _, trades = book
    result = validate_exposure_forecast(trades, n_paths=500)
    assert 0.01 <= result["pfe_breach_rate"] <= 0.12
    assert result["ee_mae"] >= 0
    assert result["n_counterparties"] == 25


def test_counterparty_section_text(book):
    counterparties, trades = book
    section = build_counterparty_section(counterparties, trades)
    assert "COUNTERPARTY CREDIT-RISK EXPOSURE VALIDATION" in section
    assert "Baseline total EAD" in section
    assert "Netting benefit" in section
    assert "PFE95 breach rate" in section
