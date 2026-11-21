"""Counterparty credit-risk exposure validation.

Extends the CCAR stress-loss validation suite with a validation module for
a counterparty credit-risk exposure model of the kind used for OTC
derivatives: Monte Carlo mark-to-market simulation, Expected Exposure (EE)
and Potential Future Exposure (PFE) profiles, Effective Expected Positive
Exposure (EPE), Exposure at Default (EAD = alpha x Effective EPE), and
stressed EAD under a parallel rate shock with widening credit spreads.

All data is synthetic and seeded. No real counterparty, trade, or market
data is used, and nothing here is a claim about any real institution.
Rate sensitivities are first-order linear approximations used for the
simulation only; they are not real DV01/Greeks calculations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42
N_COUNTERPARTIES = 25
N_TRADES = 200
N_PATHS = 2_000
N_QUARTERS = 4
ALPHA = 1.4  # Basel alpha applied to Effective EPE to get EAD.

# Illustrative one-year default probabilities by rating (synthetic).
RATING_PD = {
    "AAA": 0.0001,
    "AA": 0.0003,
    "A": 0.0007,
    "BBB": 0.0020,
    "BB": 0.0100,
    "B": 0.0400,
    "CCC": 0.1500,
}
RATINGS = list(RATING_PD)
RATING_WEIGHTS = [0.08, 0.16, 0.28, 0.28, 0.12, 0.06, 0.02]


def generate_counterparty_book(
    n_counterparties: int = N_COUNTERPARTIES,
    n_trades: int = N_TRADES,
    seed: int = RNG_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a seeded synthetic counterparty book.

    Returns (counterparties, trades). Each trade is a plain interest-rate
    swap in one counterparty's netting set, with a notional, maturity,
    current mark-to-market, direction, and a first-order rate sensitivity
    (dollars of MtM change per 1bp parallel rate move).
    """
    rng = np.random.default_rng(seed)

    ratings = rng.choice(RATINGS, size=n_counterparties, p=RATING_WEIGHTS)
    counterparties = pd.DataFrame(
        {
            "counterparty_id": np.arange(1, n_counterparties + 1),
            "rating": ratings,
            "pd_1y": [RATING_PD[r] for r in ratings],
            "lgd": np.round(rng.uniform(0.40, 0.60, n_counterparties), 2),
        }
    )

    cp_ids = rng.integers(1, n_counterparties + 1, n_trades)
    notional = rng.uniform(10_000_000, 500_000_000, n_trades)
    maturity = rng.uniform(1.0, 10.0, n_trades)
    direction = rng.choice([-1, 1], size=n_trades)  # -1 pay fixed, +1 receive fixed
    # First-order sensitivity: dollars per 1bp, roughly duration-scaled.
    rate_sens_per_bp = direction * notional * 0.0001 * np.minimum(maturity, 10.0) * 0.5
    current_mtm = np.round(
        rng.normal(0.0, 1.0, n_trades) * notional * 0.01, 2
    )

    trades = pd.DataFrame(
        {
            "trade_id": np.arange(1, n_trades + 1),
            "counterparty_id": cp_ids,
            "notional": np.round(notional, 2),
            "maturity_years": np.round(maturity, 2),
            "direction": direction,
            "rate_sens_per_bp": np.round(rate_sens_per_bp, 2),
            "current_mtm": current_mtm,
        }
    )
    return counterparties, trades


def simulate_net_mtm(
    trades: pd.DataFrame,
    n_paths: int = N_PATHS,
    n_quarters: int = N_QUARTERS,
    rate_vol_bps: float = 100.0,
    seed: int = RNG_SEED,
) -> dict[int, np.ndarray]:
    """Simulate net MtM per counterparty netting set.

    Rate moves are normal shocks with volatility growing as sqrt(time);
    each trade's MtM moves linearly with its rate sensitivity plus a small
    idiosyncratic shock. Returns {counterparty_id: array (n_paths, n_quarters)}
    of net MtM in dollars.
    """
    rng = np.random.default_rng(seed)
    times = np.arange(1, n_quarters + 1) * 0.25  # years
    result: dict[int, np.ndarray] = {}
    for cp_id, group in trades.groupby("counterparty_id"):
        sens = group["rate_sens_per_bp"].to_numpy()
        base = group["current_mtm"].to_numpy()
        # Rate shock per path per quarter (bps), volatility scales with sqrt(t).
        shocks = rng.normal(0.0, 1.0, size=(n_paths, n_quarters)) * (
            rate_vol_bps * np.sqrt(times)
        )
        # Idiosyncratic MtM noise, 0.2% of notional per trade, per quarter.
        noise = rng.normal(0.0, 1.0, size=(n_paths, n_quarters, len(group))) * (
            group["notional"].to_numpy() * 0.002
        )
        # MtM per trade: base + sens * shock + noise; net within the set.
        mtm = base[None, None, :] + sens[None, None, :] * shocks[:, :, None] + noise
        result[int(cp_id)] = mtm.sum(axis=2)
    return result


def exposure_profile(net_mtm: np.ndarray) -> pd.DataFrame:
    """EE and PFE95 profile from simulated net MtM paths (n_paths, n_quarters)."""
    positive = np.maximum(net_mtm, 0.0)
    return pd.DataFrame(
        {
            "quarter": np.arange(1, net_mtm.shape[1] + 1),
            "expected_exposure": positive.mean(axis=0),
            "pfe_95": np.quantile(positive, 0.95, axis=0),
        }
    )


def effective_epe(profile: pd.DataFrame) -> float:
    """Time-weighted average of Expected Exposure (equal quarterly weights)."""
    return float(profile["expected_exposure"].mean())


def ead_from_profile(profile: pd.DataFrame, alpha: float = ALPHA) -> float:
    """Exposure at Default = alpha x Effective EPE."""
    return alpha * effective_epe(profile)


def book_exposures(
    counterparties: pd.DataFrame,
    trades: pd.DataFrame,
    rate_shock_bps: float = 0.0,
    n_paths: int = N_PATHS,
    seed: int = RNG_SEED,
) -> pd.DataFrame:
    """EAD per counterparty, with an optional parallel rate shock applied.

    A rate shock shifts every trade's current MtM by its sensitivity times
    the shock before the simulation runs, so stressed EAD reflects the
    shocked starting point.
    """
    shifted = trades.copy()
    if rate_shock_bps:
        shifted["current_mtm"] = (
            shifted["current_mtm"] + shifted["rate_sens_per_bp"] * rate_shock_bps
        )
    net_mtm = simulate_net_mtm(shifted, n_paths=n_paths, seed=seed)
    rows = []
    for _, cp in counterparties.iterrows():
        cp_id = int(cp["counterparty_id"])
        if cp_id not in net_mtm:
            continue
        profile = exposure_profile(net_mtm[cp_id])
        ead = ead_from_profile(profile)
        rows.append(
            {
                "counterparty_id": cp_id,
                "rating": cp["rating"],
                "pd_1y": float(cp["pd_1y"]),
                "lgd": float(cp["lgd"]),
                "effective_epe": effective_epe(profile),
                "ead": ead,
                "expected_loss": ead * float(cp["pd_1y"]) * float(cp["lgd"]),
                "peak_pfe_95": float(profile["pfe_95"].max()),
            }
        )
    return pd.DataFrame(rows)


def netting_benefit(trades: pd.DataFrame) -> dict:
    """Gross vs netted current exposure: netting must never increase exposure."""
    gross = float(
        trades.groupby("counterparty_id")["current_mtm"]
        .apply(lambda s: float(np.maximum(s, 0.0).sum()))
        .sum()
    )
    netted = float(
        trades.groupby("counterparty_id")["current_mtm"]
        .sum()
        .apply(lambda v: max(v, 0.0))
        .sum()
    )
    return {
        "gross_exposure": gross,
        "netted_exposure": netted,
        "netting_benefit": gross - netted,
        "netting_benefit_pct": (gross - netted) / gross if gross > 0 else 0.0,
    }


def validate_exposure_forecast(
    trades: pd.DataFrame,
    n_paths: int = N_PATHS,
    seed: int = RNG_SEED,
) -> dict:
    """Backtest the EE forecast against a fresh-seed realised simulation.

    Forecast EE comes from ``seed``; realised exposures from ``seed + 1``.
    Also reports the PFE95 breach rate: the share of realised net exposures
    above the forecast PFE95, which should sit near 5%.
    """
    forecast = simulate_net_mtm(trades, n_paths=n_paths, seed=seed)
    realised = simulate_net_mtm(trades, n_paths=n_paths, seed=seed + 1)
    ee_errors, breaches, n_obs = [], 0, 0
    for cp_id in forecast:
        f_profile = exposure_profile(forecast[cp_id])
        r_positive = np.maximum(realised[cp_id], 0.0)
        ee_errors.extend(
            (f_profile["expected_exposure"].to_numpy() - r_positive.mean(axis=0)).tolist()
        )
        breaches += int((r_positive > f_profile["pfe_95"].to_numpy()[None, :]).sum())
        n_obs += r_positive.size
    errors = np.asarray(ee_errors, dtype=float)
    return {
        "ee_bias": float(np.mean(errors)),
        "ee_mae": float(np.mean(np.abs(errors))),
        "pfe_breach_rate": breaches / n_obs if n_obs else 0.0,
        "n_counterparties": len(forecast),
        "n_observations": n_obs,
    }



def build_counterparty_section(
    counterparties: pd.DataFrame, trades: pd.DataFrame
) -> str:
    """Assemble the counterparty exposure validation report section."""
    baseline = book_exposures(counterparties, trades)
    stressed = book_exposures(counterparties, trades, rate_shock_bps=200.0)
    total_ead = float(baseline["ead"].sum())
    total_stressed_ead = float(stressed["ead"].sum())
    uplift = total_stressed_ead - total_ead
    total_el = float(baseline["expected_loss"].sum())
    netting = netting_benefit(trades)
    validation = validate_exposure_forecast(trades, n_paths=500)

    lines = []
    lines.append("")
    lines.append("8. COUNTERPARTY CREDIT-RISK EXPOSURE VALIDATION")
    lines.append(
        f"   Book: {len(counterparties)} counterparties, {len(trades)} synthetic "
        f"interest-rate swaps; Monte Carlo MtM simulation, "
        f"{N_PATHS} paths x {N_QUARTERS} quarters."
    )
    lines.append(
        f"   Baseline total EAD: ${total_ead:,.0f}; stressed EAD (+200bp parallel "
        f"rate shock): ${total_stressed_ead:,.0f}; uplift: ${uplift:+,.0f} "
        f"({uplift / total_ead:+.1%})."
    )
    lines.append(
        f"   Total expected loss (EAD x PD x LGD): ${total_el:,.0f}; "
        f"peak PFE95 across the book: ${float(baseline['peak_pfe_95'].max()):,.0f}."
    )
    lines.append(
        f"   Netting benefit: gross ${netting['gross_exposure']:,.0f} vs netted "
        f"${netting['netted_exposure']:,.0f} "
        f"({netting['netting_benefit_pct']:.1%} reduction)."
    )
    lines.append(
        f"   Backtest (forecast EE vs fresh-seed realised): bias="
        f"${validation['ee_bias']:+,.0f}  MAE=${validation['ee_mae']:,.0f}; "
        f"PFE95 breach rate: {validation['pfe_breach_rate']:.3f} "
        f"(target ~0.05); n={validation['n_observations']}."
    )
    lines.append("   EAD by rating (baseline):")
    for rating, group in baseline.groupby("rating"):
        lines.append(
            f"   {rating:>4s}  n={len(group):>2d}  EAD=${float(group['ead'].sum()):>14,.0f}  "
            f"expected_loss=${float(group['expected_loss'].sum()):>12,.0f}"
        )
    return "\n".join(lines)
