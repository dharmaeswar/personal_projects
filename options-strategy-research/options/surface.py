"""Volatility-surface construction and arbitrage checks.

Rebuilds an implied-volatility surface from option quotes and runs the
same no-arbitrage checks a model-validation reviewer runs on a surface:
call prices fall with strike, butterfly spreads are non-negative, and
total variance does not fall with expiry.
"""

from .pricing import implied_vol


def build_surface(quotes, rate=0.05):
    """Group quotes by expiry and attach an implied vol to each quote.

    Returns {expiry_days: [quote, ...]} with an added ``implied_vol`` key
    per quote. Quotes whose price implies no vol are kept with
    ``implied_vol`` set to None.
    """
    surface = {}
    for quote in quotes:
        iv = implied_vol(quote["mid"], quote["spot"], quote["strike"],
                         quote["expiry_days"] / 365.0, rate, quote["kind"])
        enriched = dict(quote)
        enriched["implied_vol"] = iv
        surface.setdefault(quote["expiry_days"], []).append(enriched)
    return surface


def check_call_monotonicity(quotes):
    """Call prices must fall as strike rises, per expiry. Returns breaks."""
    breaks = []
    by_expiry = {}
    for quote in quotes:
        if quote["kind"] == "call":
            by_expiry.setdefault(quote["expiry_days"], []).append(quote)
    for expiry, group in by_expiry.items():
        ordered = sorted(group, key=lambda q: q["strike"])
        for lower, higher in zip(ordered, ordered[1:]):
            if higher["mid"] > lower["mid"] + 1e-9:
                breaks.append({
                    "check": "call_monotonicity", "expiry_days": expiry,
                    "strike_low": lower["strike"], "strike_high": higher["strike"],
                    "price_low": lower["mid"], "price_high": higher["mid"],
                })
    return breaks


def check_butterfly(quotes):
    """Butterfly spreads (K-dK, K, K+dK) must be non-negative. Returns breaks."""
    breaks = []
    by_expiry = {}
    for quote in quotes:
        if quote["kind"] == "call":
            by_expiry.setdefault(quote["expiry_days"], {})[quote["strike"]] = quote["mid"]
    for expiry, by_strike in by_expiry.items():
        strikes = sorted(by_strike)
        for low, mid, high in zip(strikes, strikes[1:], strikes[2:]):
            butterfly = by_strike[low] + by_strike[high] - 2.0 * by_strike[mid]
            if butterfly < -1e-9:
                breaks.append({
                    "check": "butterfly", "expiry_days": expiry,
                    "strikes": (low, mid, high), "butterfly": round(butterfly, 6),
                })
    return breaks


def check_calendar(surface):
    """Total variance (iv^2 * T) must not fall with expiry. Returns breaks."""
    breaks = []
    expiries = sorted(surface)
    atm_vol = {}
    for expiry in expiries:
        group = surface[expiry]
        atm = min(group, key=lambda q: abs(q["strike"] - q["spot"]))
        if atm["implied_vol"] is not None:
            atm_vol[expiry] = atm["implied_vol"]
    ordered = sorted(atm_vol)
    for earlier, later in zip(ordered, ordered[1:]):
        var_early = atm_vol[earlier] ** 2 * earlier / 365.0
        var_late = atm_vol[later] ** 2 * later / 365.0
        if var_late < var_early - 1e-9:
            breaks.append({
                "check": "calendar", "expiry_early": earlier,
                "expiry_late": later, "total_var_early": round(var_early, 6),
                "total_var_late": round(var_late, 6),
            })
    return breaks


def run_all_checks(quotes, rate=0.05):
    """Run every surface check. Returns (surface, breaks)."""
    surface = build_surface(quotes, rate)
    breaks = check_call_monotonicity(quotes)
    breaks += check_butterfly(quotes)
    breaks += check_calendar(surface)
    return surface, breaks
