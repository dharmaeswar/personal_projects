"""Seeded synthetic data for the MMM, attribution and geo-experiment modules.

The generative process is deliberately simple and documented, so every result
in the report can be checked against known ground truth:
- Weekly sales = base + seasonality + holiday + promo + sum of saturated,
  adstocked channel spend effects + noise.
- Geo experiment: paid social is paused in 10 treated DMAs for 8 weeks; the
  true incremental lift is a known constant per treated DMA.
- Journeys: touchpoint sequences whose conversion probability rises with the
  number and quality of touches (paid search strongest, display weakest).
"""

import numpy as np
import pandas as pd

CHANNELS = ["paid_search", "paid_social", "display", "video", "email"]
# True (pre-saturation, pre-adstock) marginal return per $1k of spend.
TRUE_BETA = {
    "paid_search": 2.6,
    "paid_social": 1.9,
    "display": 0.9,
    "video": 1.4,
    "email": 3.1,
}
# Hill saturation half-saturation points ($k of weekly spend).
TRUE_EC = {
    "paid_search": 90.0,
    "paid_social": 70.0,
    "display": 55.0,
    "video": 60.0,
    "email": 25.0,
}
ADSTOCK_THETA = 0.5
HILL_SLOPE = 1.0
BASE_SALES = 1200.0
TRUE_GEO_LIFT_PER_DMA = 45.0  # weekly incremental signups per treated DMA


def geometric_adstock(x, theta=ADSTOCK_THETA):
    """Carryover: each week's effective spend keeps theta of last week's."""
    x = np.asarray(x, dtype=float)
    out = np.zeros_like(x)
    carry = 0.0
    for i, v in enumerate(x):
        carry = v + theta * carry
        out[i] = carry
    return out


def hill(x, ec, slope=HILL_SLOPE):
    """Diminishing-returns saturation: x^slope / (x^slope + ec^slope)."""
    x = np.asarray(x, dtype=float)
    return np.power(x, slope) / (np.power(x, slope) + ec ** slope)


def generate_weekly(n_weeks=104, seed=42):
    """Weekly marketing-mix panel with known ground-truth channel effects."""
    rng = np.random.default_rng(seed)
    week = np.arange(n_weeks)
    season = 120.0 * np.sin(2 * np.pi * week / 52.0)
    holiday = np.where((week % 52 >= 47) | (week % 52 <= 1), 150.0, 0.0)
    promo = rng.choice([0.0, 80.0], size=n_weeks, p=[0.85, 0.15])

    spend = {}
    # Each channel follows its own 26-week budget cycle (different phase),
    # so weekly spend swings enough for the MMM to identify each channel's
    # effect instead of drowning in the sales noise.
    phases = {"paid_search": 0.0, "paid_social": 1.3, "display": 2.6,
              "video": 3.9, "email": 5.2}
    for ch in CHANNELS:
        level = {"paid_search": 80, "paid_social": 60, "display": 45,
                 "video": 50, "email": 18}[ch]
        cycle = 1.0 + 0.5 * np.sin(2 * np.pi * week / 26.0 + phases[ch])
        spend[ch] = np.maximum(
            0.0, level * cycle * (1.0 + rng.normal(0.0, 0.20, size=n_weeks)))
    spend["organic_search"] = np.zeros(n_weeks)

    sales = BASE_SALES + season + holiday + promo
    contributions = {}
    for ch in CHANNELS:
        effective = hill(geometric_adstock(spend[ch]), TRUE_EC[ch]) * TRUE_EC[ch]
        contrib = TRUE_BETA[ch] * effective
        contributions[ch] = contrib
        sales = sales + contrib
    sales = sales + rng.normal(0.0, 8.0, size=n_weeks)

    df = pd.DataFrame({"week": week, "sales": sales, "seasonality": season,
                       "holiday": holiday, "promo": promo})
    for ch in CHANNELS:
        df[f"spend_{ch}"] = spend[ch]
        df[f"true_contrib_{ch}"] = contributions[ch]
    return df


def generate_geo(n_geos=40, n_treated=10, n_pre=12, n_post=8, seed=7):
    """DMA-level geo holdout: paid social paused in treated DMAs post-period.

    Weekly signups per DMA = DMA baseline (persistent) + weekly noise +
    the paid-social effect, which is removed in treated DMAs during the
    post period. The removed effect is TRUE_GEO_LIFT_PER_DMA per DMA-week.
    """
    rng = np.random.default_rng(seed)
    geos = [f"DMA_{i:02d}" for i in range(n_geos)]
    treated = set(rng.choice(geos, size=n_treated, replace=False))
    rows = []
    baseline = {g: rng.normal(300.0, 60.0) for g in geos}
    for g in geos:
        for w in range(n_pre + n_post):
            period = "pre" if w < n_pre else "post"
            is_treated = g in treated
            social_effect = TRUE_GEO_LIFT_PER_DMA
            if period == "post" and is_treated:
                social_effect = 0.0  # channel paused in treated DMAs
            signups = baseline[g] + social_effect + rng.normal(0.0, 25.0)
            rows.append({
                "geo": g, "week": w, "period": period,
                "treated": int(is_treated), "signups": signups,
            })
    return pd.DataFrame(rows)


# Journey conversion model: base rate plus per-touch lift (log-odds scale).
TOUCH_LIFT = {
    "paid_search": 0.9, "paid_social": 0.5, "display": 0.2,
    "video": 0.6, "email": 0.8, "organic_search": 0.7,
}
BASE_LOGIT = -2.2
# Independent per-channel inclusion probability in a journey (not a fixed
# touch count: with a fixed count, adding a weak channel could *displace* a
# strong one and lower conversions, which would make Shapley values negative
# for a purely mechanical reason. Independent inclusion keeps every
# channel's marginal contribution non-negative, as it should be here.)
TOUCH_PROBS = {
    "paid_search": 0.45, "paid_social": 0.38, "display": 0.25,
    "video": 0.22, "email": 0.18, "organic_search": 0.20,
}


def _conversion_prob(touches):
    logit = BASE_LOGIT + sum(TOUCH_LIFT[t] for t in touches)
    return 1.0 / (1.0 + np.exp(-logit))


def _draw_touches(rng, channels):
    """One journey's touch set: each channel included independently.

    Journeys may be empty (no tracked touch) — those convert at the base
    rate and are excluded from attribution shares, which are computed over
    converted journeys with at least one touch. Nothing is forced: forcing
    a touch would let a weak channel displace a strong one in small
    coalitions and bias Shapley values downward.
    """
    touches = [c for c in channels if rng.random() < TOUCH_PROBS[c]]
    rng.shuffle(touches)
    return touches


def generate_journeys(n=20000, seed=11):
    """Synthetic user journeys: independent touch inclusion, then a draw."""
    rng = np.random.default_rng(seed)
    channels = list(TOUCH_PROBS)
    rows = []
    for _ in range(n):
        touches = _draw_touches(rng, channels)
        p = _conversion_prob(touches)
        rows.append({"touches": touches, "converted": int(rng.random() < p)})
    return pd.DataFrame(rows)


def subset_conversion_rate(subset, n=4000, seed=99):
    """Conversion rate when only `subset` channels may appear in journeys."""
    rng = np.random.default_rng(seed)
    channels = list(subset)
    if not channels:
        p = 1.0 / (1.0 + np.exp(-BASE_LOGIT))
        return float(rng.binomial(n, p) / n)
    conv = 0
    for _ in range(n):
        touches = _draw_touches(rng, channels)
        if rng.random() < _conversion_prob(touches):
            conv += 1
    return conv / n
