"""Prepayment model validation: challenge the agency prepayment model.

A prepayment model that feeds trading decisions needs independent
validation, not just a fit. This module runs the validation battery a
model-validation team applies to an agency prepayment model built on the
PSA benchmark plus a refinancing incentive:

- **Decomposition** — split observed CPR into a turnover component
  (housing turnover: moves, defaults, cash-outs that happen at any rate)
  and a refinancing component driven by the rate incentive.
- **Seasoning** — new pools prepay slowly and ramp up as loans season;
  the ramp must rise with loan age and plateau, never jump.
- **Burnout** — after a refinancing wave, the remaining pool is made of
  borrowers who did not refinance when they could have, so the same
  incentive produces less prepayment over time; the response must decay.
- **Incentive response** — CPR must fall monotonically as the mortgage
  rate rises (a higher rate means less incentive to refinance).
- **Backtest** — forecast CPR against realised CPR month by month, with
  error metrics (bias, MAE, RMSE) and a tolerance check.

All inputs are synthetic; nothing here is a claim about any real pool.
"""

from __future__ import annotations

import numpy as np

from .prepayment import incentive_multiplier, monthly_cpr, psa_cpr

# A model that misses realised CPR by more than 2 points on average fails.
MAX_MEAN_ABS_ERROR = 0.02
# Turnover (non-refi) prepayment: 2% CPR is the long-run housing baseline.
BASE_TURNOVER_CPR = 0.02


def decompose_cpr(cpr: float, turnover_cpr: float = BASE_TURNOVER_CPR) -> dict:
    """Split a CPR into turnover and refinancing components.

    Turnover is the rate-insensitive floor; the rest is refinancing.
    A negative refinancing component means the inputs are inconsistent.
    """
    if not 0.0 <= cpr < 1.0:
        raise ValueError("CPR must be in [0, 1)")
    if not 0.0 <= turnover_cpr <= cpr:
        raise ValueError("turnover CPR must be between 0 and the total CPR")
    refi = cpr - turnover_cpr
    return {"cpr": cpr, "turnover_cpr": turnover_cpr,
            "refi_cpr": refi, "refi_share": refi / cpr if cpr else 0.0}


def seasoning_factor(month: int) -> float:
    """Seasoning ramp: 0 at origination, rising to 1.0 by month 30.

    Mirrors the PSA ramp so a validation can check the model's own ramp
    against the benchmark shape instead of trusting it.
    """
    if month < 1:
        raise ValueError("month is 1-based")
    return min(month, 30) / 30.0


def burnout_factor(months_since_peak: int, half_life_months: int = 12) -> float:
    """Burnout decay: the refi response halves every ``half_life_months``.

    After a refinancing wave peaks, the surviving pool is less responsive
    to the same incentive, so the multiplier on the refi component decays.
    """
    if months_since_peak < 0:
        raise ValueError("months_since_peak must be >= 0")
    return 0.5 ** (months_since_peak / half_life_months)


def backtest(forecast_cpr: list[float], actual_cpr: list[float]) -> dict:
    """Score forecast CPR against realised CPR, month by month."""
    if len(forecast_cpr) != len(actual_cpr):
        raise ValueError("forecast and actual must have the same length")
    if not forecast_cpr:
        raise ValueError("need at least one month to backtest")
    forecast = np.asarray(forecast_cpr, dtype=float)
    actual = np.asarray(actual_cpr, dtype=float)
    errors = forecast - actual
    return {
        "months": len(forecast),
        "bias": float(np.mean(errors)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "max_abs_error": float(np.max(np.abs(errors))),
        "within_tolerance": bool(np.mean(np.abs(errors)) <= MAX_MEAN_ABS_ERROR),
    }


def incentive_response_curve(wac: float, mortgage_rates: list[float],
                             month: int = 36, psa: float = 100.0) -> list[dict]:
    """CPR at each mortgage rate, for the monotonicity check."""
    return [{"mortgage_rate": rate,
             "cpr": monthly_cpr(month, wac, rate, psa)}
            for rate in mortgage_rates]


def validate_model(wac: float, mortgage_rate: float, psa: float = 100.0,
                   forecast_cpr: list[float] | None = None,
                   actual_cpr: list[float] | None = None) -> dict:
    """Run the full validation battery; return findings with pass/fail."""
    findings: list[dict] = []

    # 1. Incentive response must fall as the mortgage rate rises.
    rates = [mortgage_rate - 0.02, mortgage_rate - 0.01, mortgage_rate,
             mortgage_rate + 0.01, mortgage_rate + 0.02]
    curve = incentive_response_curve(wac, rates)
    cprs = [point["cpr"] for point in curve]
    monotonic = all(cprs[i] >= cprs[i + 1] for i in range(len(cprs) - 1))
    findings.append({
        "check": "incentive response monotonic in mortgage rate",
        "passed": monotonic,
        "detail": f"CPR {cprs[0]:.4f} -> {cprs[-1]:.4f} as rate rises 4 points",
    })

    # 2. Seasoning must ramp up and plateau, never exceed 1.0.
    ramp = [seasoning_factor(m) for m in (1, 6, 12, 30, 60)]
    ramp_ok = ramp == sorted(ramp) and ramp[-1] == 1.0 and ramp[-2] == 1.0
    findings.append({
        "check": "seasoning ramp rises and plateaus at 1.0",
        "passed": ramp_ok,
        "detail": f"factors at months 1/6/12/30/60: {[round(r, 2) for r in ramp]}",
    })

    # 3. Burnout must decay the refi response over time.
    decay = [burnout_factor(m) for m in (0, 12, 24)]
    decay_ok = decay == sorted(decay, reverse=True) and decay[1] == 0.5
    findings.append({
        "check": "burnout decays refi response with a 12-month half-life",
        "passed": decay_ok,
        "detail": f"factors at 0/12/24 months: {[round(d, 2) for d in decay]}",
    })

    # 4. CPR must stay inside the model's own bounds at the current rate.
    current = monthly_cpr(36, wac, mortgage_rate, psa)
    bounds_ok = 0.0 <= current <= 0.50
    findings.append({
        "check": "model CPR inside [0, 0.50] at current rate",
        "passed": bounds_ok,
        "detail": f"CPR {current:.4f} at month 36",
    })

    # 5. Backtest against realised CPR, when history is supplied.
    if forecast_cpr is not None and actual_cpr is not None:
        result = backtest(forecast_cpr, actual_cpr)
        findings.append({
            "check": "backtest mean absolute error within 2 points",
            "passed": result["within_tolerance"],
            "detail": f"MAE {result['mae']:.4f}, bias {result['bias']:+.4f}, "
                      f"RMSE {result['rmse']:.4f} over {result['months']} months",
        })

    passed = sum(1 for f in findings if f["passed"])
    return {"findings": findings, "passed": passed,
            "failed": len(findings) - passed,
            "model_fit_for_use": passed == len(findings)}
