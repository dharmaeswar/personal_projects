"""Single-stock KPI inflection analysis for long/short equities research.

Extends the research assistant with the quantitative half of a PM team's
workflow: track company KPIs (revenue growth, operating margin) and an
alternative-data proxy across quarters, flag inflections, forecast the next
quarter with a regression, score each name, and backtest the resulting
long/short signal. All data is synthetic and seeded for fictional companies
(the same four names as the research-notes corpus). No real filings,
earnings, market data, or live returns are used.
"""

import math
import random
from dataclasses import dataclass, field

COMPANIES = [
    "Acme Industrial Holdings",
    "Beacon Health Systems",
    "Northwind Energy Partners",
    "Helix Software Group",
]

QUARTERS = [
    "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
    "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4",
    "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4",
]

# Planted inflections (the seeded "truth" the detector must find):
# Helix revenue growth steps up from 2025-Q3; Northwind operating margin
# steps down from 2026-Q1. Everything else drifts mildly around its base.
_BASE = {
    "Acme Industrial Holdings": {"rev": 6.0, "margin": 18.0, "alt": 100.0},
    "Beacon Health Systems": {"rev": 3.0, "margin": 12.0, "alt": 100.0},
    "Northwind Energy Partners": {"rev": 4.0, "margin": 22.0, "alt": 100.0},
    "Helix Software Group": {"rev": 8.0, "margin": 15.0, "alt": 100.0},
}


@dataclass
class CompanyKPI:
    company: str
    quarters: list = field(default_factory=list)
    revenue_growth: list = field(default_factory=list)  # % YoY
    operating_margin: list = field(default_factory=list)  # %
    alt_index: list = field(default_factory=list)  # alt-data proxy, base 100
    stock_return: list = field(default_factory=list)  # % next-quarter return


def load_kpi_panel(seed=20261126):
    """Build the seeded 4-company x 12-quarter KPI panel.

    Deterministic for a given seed. Revenue growth and margins are random
    walks around company bases with two planted level shifts (see _BASE
    comment). The alt-data index trends with revenue growth plus noise.
    Next-quarter stock returns are seeded noise plus a KPI-surprise term
    (revenue growth minus its trailing 4-quarter mean), so a KPI signal
    has something real to find without claiming a tradable edge.
    """
    rng = random.Random(seed)
    panel = []
    for company in COMPANIES:
        base = _BASE[company]
        rev, margin, alt, rets = [], [], [], []
        rev_level, margin_level, alt_level = base["rev"], base["margin"], base["alt"]
        for i, _quarter in enumerate(QUARTERS):
            if company == "Helix Software Group" and i == 6:
                rev_level += 10.0  # inflection up: growth steps 8% -> ~18%
            if company == "Northwind Energy Partners" and i == 8:
                margin_level -= 7.0  # inflection down: margin steps 22% -> ~15%
            rev_level += rng.uniform(-0.6, 0.6)
            margin_level += rng.uniform(-0.5, 0.5)
            alt_level *= 1.0 + (rev_level - base["rev"]) / 400.0 + rng.uniform(-0.01, 0.01)
            rev.append(round(rev_level, 2))
            margin.append(round(margin_level, 2))
            alt.append(round(alt_level, 1))
            # Seeded return for the quarter that just ended, driven by the
            # KPI surprise (current growth vs trailing 4-quarter mean).
            surprise = rev_level - (sum(rev[-5:-1]) / 4.0 if len(rev) > 4 else base["rev"])
            rets.append(round(rng.uniform(-3.0, 3.0) + 0.8 * surprise, 2))
        panel.append(CompanyKPI(
            company=company, quarters=list(QUARTERS),
            revenue_growth=rev, operating_margin=margin,
            alt_index=alt, stock_return=rets,
        ))
    return panel


def detect_inflections(values, window=4, threshold=2.0):
    """Flag quarters where a KPI breaks from its trailing window.

    For each index i >= window, compare values[i] with the mean and
    standard deviation of the previous `window` values. Flag when
    |z| >= threshold. Returns a list of dicts with index, value, z-score
    and direction ("up" / "down"). A flat trailing window (std ~ 0) is
    treated as no break unless the move itself is large.
    """
    if len(values) < window + 1:
        return []
    out = []
    for i in range(window, len(values)):
        trail = values[i - window:i]
        mean = sum(trail) / window
        var = sum((v - mean) ** 2 for v in trail) / window
        std = math.sqrt(var)
        move = values[i] - mean
        if std < 1e-9:
            flagged = abs(move) >= threshold
            z = math.copysign(threshold, move) if flagged else 0.0
        else:
            z = move / std
            flagged = abs(z) >= threshold
        if flagged:
            out.append({
                "index": i, "value": values[i], "z": round(z, 2),
                "direction": "up" if move > 0 else "down",
            })
    return out


def forecast_kpi(values, horizon=1):
    """OLS forecast of a KPI series: fit value ~ time index, extrapolate.

    Returns {"forecast": ..., "slope": ..., "intercept": ..., "r_squared": ...}.
    A positive slope means the KPI is trending up over the sample.
    """
    n = len(values)
    if n < 3:
        raise ValueError("forecast_kpi needs at least 3 observations")
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    slope = sxy / sxx if sxx else 0.0
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in xs]
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    ss_res = sum((y - f) ** 2 for y, f in zip(values, fitted))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    forecast = intercept + slope * (n - 1 + horizon)
    return {
        "forecast": round(forecast, 2),
        "slope": round(slope, 3),
        "intercept": round(intercept, 2),
        "r_squared": round(r2, 3),
    }


def alt_momentum(alt_index, window=4):
    """Percent change of the alt-data index over the last `window` quarters."""
    if len(alt_index) < window + 1:
        raise ValueError("alt_momentum needs at least window + 1 observations")
    start = alt_index[-window - 1]
    end = alt_index[-1]
    return round(100.0 * (end - start) / start, 2) if start else 0.0


def kpi_signal(company, upto=None):
    """Score one company from its KPI data through quarter index `upto`.

    Components (each -1 / 0 / +1): latest revenue-growth inflection
    direction, sign of the revenue-growth forecast slope, sign of the
    alt-data momentum (beyond +/-5%). Score ranges from -3 (deteriorating
    on every read) to +3 (improving on every read). `upto` caps the data
    used, so a backtest signal at quarter t never sees data after t.
    """
    upto = len(company.quarters) - 1 if upto is None else upto
    rev = company.revenue_growth[:upto + 1]
    alt = company.alt_index[:upto + 1]
    inflections = detect_inflections(rev)
    latest = inflections[-1] if inflections else None
    inflect = 0
    if latest is not None and latest["index"] == upto:
        inflect = 1 if latest["direction"] == "up" else -1
    slope = forecast_kpi(rev)["slope"]
    trend = 1 if slope > 0 else (-1 if slope < 0 else 0)
    momentum = alt_momentum(alt)
    alt_sign = 1 if momentum > 5.0 else (-1 if momentum < -5.0 else 0)
    return {
        "company": company.company,
        "score": inflect + trend + alt_sign,
        "inflection": inflect,
        "trend": trend,
        "alt_momentum_pct": momentum,
        "alt_sign": alt_sign,
        "latest_inflection": latest,
    }


def backtest_kpi_signal(panel, cost_bps=5):
    """Quarterly long/short backtest of the KPI signal (no look-ahead).

    At the end of each quarter t (from the 5th quarter on, so the signal
    has a trailing window), rank names by signal score: long the top name,
    short the bottom name, hold for quarter t+1, and charge `cost_bps` on
    the two-way turnover. Returns per-trade rows plus summary metrics.
    """
    trades = []
    n_quarters = len(panel[0].quarters)
    for t in range(4, n_quarters - 1):
        signals = [kpi_signal(c, upto=t) for c in panel]
        ranked = sorted(signals, key=lambda s: (s["score"], s["company"]))
        short_name, long_name = ranked[0]["company"], ranked[-1]["company"]
        if long_name == short_name:
            continue
        long_ret = next(c.stock_return[t + 1] for c in panel if c.company == long_name)
        short_ret = next(c.stock_return[t + 1] for c in panel if c.company == short_name)
        gross = long_ret - short_ret
        cost = 2.0 * cost_bps / 100.0
        trades.append({
            "formation_quarter": panel[0].quarters[t],
            "holding_quarter": panel[0].quarters[t + 1],
            "long": long_name, "short": short_name,
            "long_return_pct": long_ret, "short_return_pct": short_ret,
            "net_return_pct": round(gross - cost, 2),
        })
    wins = sum(1 for tr in trades if tr["net_return_pct"] > 0)
    total = round(sum(tr["net_return_pct"] for tr in trades), 2)
    return {
        "trades": trades,
        "n_trades": len(trades),
        "hit_rate": round(wins / len(trades), 3) if trades else 0.0,
        "mean_quarterly_return_pct": round(total / len(trades), 2) if trades else 0.0,
        "total_return_pct": total,
    }


def dashboard_summary(panel):
    """One row per company: latest KPIs, inflections, forecast, signal."""
    rows = []
    for company in panel:
        rev = company.revenue_growth
        margin = company.operating_margin
        rev_inflect = detect_inflections(rev)
        margin_inflect = detect_inflections(margin)
        forecast = forecast_kpi(rev)
        signal = kpi_signal(company)
        rows.append({
            "company": company.company,
            "latest_revenue_growth_pct": rev[-1],
            "latest_operating_margin_pct": margin[-1],
            "latest_alt_index": company.alt_index[-1],
            "alt_momentum_pct": signal["alt_momentum_pct"],
            "revenue_inflections": rev_inflect,
            "margin_inflections": margin_inflect,
            "next_quarter_revenue_growth_forecast_pct": forecast["forecast"],
            "revenue_trend_slope": forecast["slope"],
            "revenue_forecast_r_squared": forecast["r_squared"],
            "signal_score": signal["score"],
            "position": "LONG" if signal["score"] >= 2 else (
                "SHORT" if signal["score"] <= -2 else "NEUTRAL"),
        })
    return rows


def kpi_report(panel=None):
    """One-call summary: dashboard rows plus the signal backtest."""
    panel = panel or load_kpi_panel()
    return {
        "quarters": list(panel[0].quarters),
        "dashboard": dashboard_summary(panel),
        "backtest": backtest_kpi_signal(panel),
    }
