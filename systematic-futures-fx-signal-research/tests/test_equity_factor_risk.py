"""Tests for the equity factor-risk module (Axioma-style analytics)."""

import numpy as np
import pandas as pd
import pytest

from sys_signal_research.equity_factor_risk import (
    FACTORS,
    estimate_factor_betas,
    factor_risk_decomposition,
    generate_equity_panel,
    governance_checks,
    portfolio_risk_summary,
    tracking_error,
)


@pytest.fixture(scope="module")
def panel():
    return generate_equity_panel(seed=42, n_stocks=40, n_days=504)


def test_panel_is_seeded_and_shaped(panel):
    stock_returns, factor_returns, true_betas, sectors = panel
    assert stock_returns.shape == (504, 40)
    assert list(factor_returns.columns) == FACTORS
    assert true_betas.shape == (40, 5)
    assert len(sectors) == 40
    again = generate_equity_panel(seed=42, n_stocks=40, n_days=504)
    pd.testing.assert_frame_equal(stock_returns, again[0])


def test_estimated_betas_recover_true_betas(panel):
    stock_returns, factor_returns, true_betas, _ = panel
    est = estimate_factor_betas(stock_returns, factor_returns)
    assert est["betas"].shape == true_betas.shape
    corr = np.corrcoef(est["betas"].values.ravel(), true_betas.values.ravel())[0, 1]
    assert corr > 0.9
    assert est["r_squared"].median() > 0.25


def test_tracking_error_zero_for_identical_series(panel):
    stock_returns, _, _, _ = panel
    bench = stock_returns.mean(axis=1)
    assert tracking_error(bench, bench) == 0.0
    assert tracking_error(bench, bench, annualised=False) == 0.0


def test_tracking_error_positive_and_annualised(panel):
    stock_returns, _, _, _ = panel
    port = stock_returns.iloc[:, 0]
    bench = stock_returns.mean(axis=1)
    assert tracking_error(port, bench) > tracking_error(port, bench, annualised=False) > 0


def test_risk_decomposition_variance_adds_up(panel):
    stock_returns, factor_returns, _, _ = panel
    est = estimate_factor_betas(stock_returns, factor_returns)
    weights = pd.Series(1.0 / 40, index=est["betas"].index)
    factor_cov = factor_returns.cov() * 252
    idio_var = (est["residual_std"] ** 2) * 252
    decomp = factor_risk_decomposition(weights, est["betas"], factor_cov, idio_var)
    assert decomp["total_variance"] == pytest.approx(
        decomp["factor_variance"] + decomp["specific_variance"]
    )
    assert decomp["total_vol"] == pytest.approx(np.sqrt(decomp["total_variance"]))
    assert decomp["factor_vol"] > 0
    assert decomp["specific_vol"] > 0
    assert abs(decomp["factor_exposures"]["Market"] - 1.0) < 0.3


def test_risk_summary_has_all_sections(panel):
    stock_returns, factor_returns, _, sectors = panel
    est = estimate_factor_betas(stock_returns, factor_returns)
    weights = pd.Series(1.0 / 40, index=est["betas"].index)
    bench = stock_returns.mean(axis=1)
    summary = portfolio_risk_summary(
        weights, stock_returns, factor_returns, est["betas"], bench, sectors
    )
    assert summary["n_positions"] == 40
    assert 0 < summary["total_vol"] < 1.0
    assert summary["tracking_error"] >= 0
    assert len(summary["top_factor_tilts"]) == 3
    assert len(summary["largest_positions"]) == 5
    assert abs(sum(summary["sector_exposures"].values()) - 1.0) < 1e-9
    assert 0 < summary["concentration_hhi"] <= 1.0


def test_governance_checks_pass_on_clean_panel(panel):
    stock_returns, factor_returns, _, _ = panel
    est = estimate_factor_betas(stock_returns, factor_returns)
    checks = governance_checks(
        stock_returns, factor_returns, est["betas"], est["r_squared"], est["residuals"]
    )
    by_name = {c["check"]: c for c in checks}
    assert set(by_name) == {
        "missing_data",
        "stale_factors",
        "low_explanatory_power",
        "residual_autocorrelation",
        "beta_stability",
        "factor_collinearity",
    }
    assert by_name["missing_data"]["status"] == "pass"
    assert by_name["stale_factors"]["status"] == "pass"
    assert by_name["beta_stability"]["status"] == "pass"
    assert all(c["status"] in ("pass", "warn", "fail") for c in checks)


def test_governance_flags_constant_factor(panel):
    stock_returns, factor_returns, _, _ = panel
    broken = factor_returns.copy()
    broken["Quality"] = 0.001
    est = estimate_factor_betas(stock_returns, broken)
    checks = governance_checks(
        stock_returns, broken, est["betas"], est["r_squared"], est["residuals"]
    )
    by_name = {c["check"]: c for c in checks}
    assert by_name["stale_factors"]["status"] == "fail"


def test_governance_flags_missing_data(panel):
    stock_returns, factor_returns, _, _ = panel
    gappy = stock_returns.copy()
    gappy.iloc[:50, :5] = np.nan
    est = estimate_factor_betas(gappy, factor_returns)
    checks = governance_checks(gappy, factor_returns, est["betas"], est["r_squared"], est["residuals"])
    by_name = {c["check"]: c for c in checks}
    assert by_name["missing_data"]["status"] in ("warn", "fail")
