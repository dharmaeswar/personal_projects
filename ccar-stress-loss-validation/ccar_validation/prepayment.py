"""Agency mortgage prepayment model validation.

Extends the CCAR stress-loss validation suite with a validation module for
an agency prepayment model of the kind used for Agency MBS: conditional
prepayment rates (CPR), the PSA benchmark, rate-incentive sensitivity, and
seasoning / burnout behaviour.

All data is synthetic and seeded. No real loan, agency, or market data is
used, and nothing here is a claim about any real institution or security.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42
N_LOANS = 3_000

# PSA benchmark: 100 PSA ramps linearly to a 6% annual CPR over 30 months.
PSA_FULL_CPR = 0.06
PSA_RAMP_MONTHS = 30


def seasoning_factor(loan_age_months: np.ndarray | float) -> np.ndarray:
    """PSA-style seasoning ramp: 0 at origination, 1.0 after 30 months."""
    age = np.asarray(loan_age_months, dtype=float)
    return np.clip(age / PSA_RAMP_MONTHS, 0.0, 1.0)


def cpr_from_psa(psa_speed: float, loan_age_months: np.ndarray | float) -> np.ndarray:
    """CPR implied by a PSA speed (100 PSA = 6% CPR once fully seasoned)."""
    if psa_speed < 0:
        raise ValueError("PSA speed must be non-negative")
    return PSA_FULL_CPR * (psa_speed / 100.0) * seasoning_factor(loan_age_months)


def rate_incentive(coupon_rate: np.ndarray, current_rate: np.ndarray) -> np.ndarray:
    """Refinancing incentive in percentage points: coupon minus current rate."""
    return np.asarray(coupon_rate, dtype=float) - np.asarray(current_rate, dtype=float)


def _refi_component(incentive: np.ndarray) -> np.ndarray:
    """Refi-driven CPR component: logistic in the rate incentive.

    Near zero when the loan is out of the money, rising to ~24% CPR when
    the incentive is large (coupon well above the current rate).
    """
    return 0.24 / (1.0 + np.exp(-2.5 * (np.asarray(incentive, dtype=float) - 0.75)))


def _turnover_component(fico: np.ndarray, ltv: np.ndarray) -> np.ndarray:
    """Baseline housing-turnover CPR component (about 4-8% a year)."""
    fico = np.asarray(fico, dtype=float)
    ltv = np.asarray(ltv, dtype=float)
    return 0.06 + 0.01 * (fico - 700.0) / 100.0 - 0.01 * (ltv - 70.0) / 20.0


def _burnout_factor(burnout_months: np.ndarray) -> np.ndarray:
    """Burnout: pools exposed to low rates for longer prepay more slowly."""
    return np.exp(-np.asarray(burnout_months, dtype=float) / 36.0)


def predict_cpr(df: pd.DataFrame) -> np.ndarray:
    """Model CPR forecast (fraction per year, 0-1) for a prepayment pool."""
    incentive = rate_incentive(df["coupon_rate"].to_numpy(), df["current_rate"].to_numpy())
    seasoning = seasoning_factor(df["loan_age_months"].to_numpy())
    refi = _refi_component(incentive)
    turnover = _turnover_component(df["fico_score"].to_numpy(), df["ltv"].to_numpy())
    burnout = _burnout_factor(df["burnout_months"].to_numpy())
    cpr = seasoning * (turnover + refi * burnout)
    return np.clip(cpr, 0.0, 0.60)


def generate_prepayment_pool(n_loans: int = N_LOANS, seed: int = RNG_SEED) -> pd.DataFrame:
    """Generate a seeded synthetic agency mortgage pool with observed CPR.

    Observed CPR follows the same drivers as the model (seasoning, rate
    incentive, turnover, burnout) plus noise, so the model has real signal
    to find but is not perfect.
    """
    rng = np.random.default_rng(seed)
    loan_age_months = rng.integers(1, 121, size=n_loans)
    coupon_rate = rng.normal(6.5, 1.2, n_loans).clip(3.0, 10.0)
    current_rate = rng.normal(6.0, 1.0, n_loans).clip(3.0, 9.5)
    balance = rng.lognormal(np.log(300_000.0), 0.5, n_loans)
    fico = rng.normal(740.0, 45.0, n_loans).clip(620.0, 850.0)
    ltv = rng.normal(75.0, 12.0, n_loans).clip(40.0, 97.0)
    burnout_months = rng.exponential(scale=12.0, size=n_loans).clip(0.0, 60.0)

    pool = pd.DataFrame(
        {
            "loan_id": np.arange(n_loans),
            "loan_age_months": loan_age_months,
            "coupon_rate": np.round(coupon_rate, 2),
            "current_rate": np.round(current_rate, 2),
            "balance": np.round(balance, 2),
            "fico_score": np.round(fico).astype(int),
            "ltv": np.round(ltv, 1),
            "burnout_months": np.round(burnout_months, 1),
        }
    )
    # Observed CPR: model form with slightly different coefficients + noise,
    # so validation measures a real (small) model error rather than zero.
    incentive = rate_incentive(pool["coupon_rate"].to_numpy(), pool["current_rate"].to_numpy())
    seasoning = seasoning_factor(pool["loan_age_months"].to_numpy())
    refi_obs = 0.22 / (1.0 + np.exp(-2.2 * (incentive - 0.85)))
    turnover_obs = 0.055 + 0.012 * (pool["fico_score"].to_numpy() - 700.0) / 100.0
    burnout_obs = np.exp(-pool["burnout_months"].to_numpy() / 30.0)
    true_cpr = seasoning * (turnover_obs + refi_obs * burnout_obs)
    observed = np.clip(true_cpr + rng.normal(0.0, 0.01, n_loans), 0.0, 0.60)
    pool["observed_cpr"] = np.round(observed, 4)
    return pool


def validate_prepayment_model(
    actual: np.ndarray, predicted: np.ndarray, tolerance: float = 0.02
) -> dict:
    """Outcomes-analysis metrics for a prepayment model (CPR, fraction/year)."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    err = predicted - actual
    return {
        "bias": float(np.mean(err)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "hit_rate": float(np.mean(np.abs(err) <= tolerance)),
        "n": int(len(actual)),
    }


def sensitivity_table(
    pool: pd.DataFrame, rate_shocks_bps: tuple = (-200, -100, 0, 100, 200)
) -> pd.DataFrame:
    """Mean forecast CPR under parallel shifts to the current mortgage rate.

    A sound prepayment model must be monotone: CPR falls as rates rise.
    """
    rows = []
    for shock in rate_shocks_bps:
        shifted = pool.copy()
        shifted["current_rate"] = (shifted["current_rate"] + shock / 100.0).clip(2.0, 12.0)
        preds = predict_cpr(shifted)
        rows.append(
            {
                "rate_shock_bps": int(shock),
                "mean_forecast_cpr": float(np.mean(preds)),
                "median_forecast_cpr": float(np.median(preds)),
            }
        )
    return pd.DataFrame(rows)


def check_monotonicity(table: pd.DataFrame) -> bool:
    """True when mean forecast CPR strictly falls as the rate shock rises."""
    cpr = table.sort_values("rate_shock_bps")["mean_forecast_cpr"].to_numpy()
    return bool(np.all(np.diff(cpr) < 0))


def calibration_by_incentive(
    actual: np.ndarray, predicted: np.ndarray, incentive: np.ndarray, n_bins: int = 5
) -> pd.DataFrame:
    """Mean actual vs predicted CPR by rate-incentive bucket."""
    frame = pd.DataFrame(
        {
            "incentive": np.asarray(incentive, dtype=float),
            "actual": np.asarray(actual, dtype=float),
            "predicted": np.asarray(predicted, dtype=float),
        }
    )
    frame["bucket"] = pd.qcut(frame["incentive"], q=n_bins, duplicates="drop")
    grouped = frame.groupby("bucket", observed=True).agg(
        n=("actual", "size"),
        mean_actual=("actual", "mean"),
        mean_predicted=("predicted", "mean"),
    )
    grouped["calibration_gap"] = grouped["mean_predicted"] - grouped["mean_actual"]
    return grouped.reset_index()


def build_prepayment_section(pool: pd.DataFrame) -> str:
    """Assemble the prepayment validation report section as plain text."""
    actual = pool["observed_cpr"].to_numpy()
    predicted = predict_cpr(pool)
    metrics = validate_prepayment_model(actual, predicted)
    sens = sensitivity_table(pool)
    incentive = rate_incentive(pool["coupon_rate"].to_numpy(), pool["current_rate"].to_numpy())
    cal = calibration_by_incentive(actual, predicted, incentive)
    monotone = check_monotonicity(sens)
    mean_cpr = float(np.mean(actual))

    lines = []
    lines.append("")
    lines.append("7. AGENCY PREPAYMENT MODEL VALIDATION")
    lines.append(f"   Pool: {len(pool)} synthetic agency loans; mean observed CPR: {mean_cpr:.4f}.")
    lines.append(
        f"   Outcomes: bias={metrics['bias']:+.4f}  MAE={metrics['mae']:.4f}  "
        f"RMSE={metrics['rmse']:.4f}  hit_rate={metrics['hit_rate']:.3f}  n={metrics['n']}"
    )
    lines.append("   Rate sensitivity (mean forecast CPR by parallel rate shock):")
    for _, row in sens.iterrows():
        lines.append(
            f"   {int(row['rate_shock_bps']):>+5d} bps  mean_cpr={row['mean_forecast_cpr']:.4f}  "
            f"median_cpr={row['median_forecast_cpr']:.4f}"
        )
    lines.append(
        f"   Monotonicity check (CPR falls as rates rise): {'PASS' if monotone else 'FAIL'}."
    )
    lines.append("   Calibration by rate-incentive bucket (mean actual vs predicted CPR):")
    for _, row in cal.iterrows():
        lines.append(
            f"   {str(row['bucket']):>22s}  n={int(row['n']):>5d}  "
            f"actual={row['mean_actual']:.4f}  predicted={row['mean_predicted']:.4f}  "
            f"gap={row['calibration_gap']:+.4f}"
        )
    return "\n".join(lines)
