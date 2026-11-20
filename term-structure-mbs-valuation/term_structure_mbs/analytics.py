"""Risk analytics: effective duration / convexity and rate-scenario prices."""

from __future__ import annotations

from .mbs import static_price


def effective_duration_convexity(pool, curve, bump: float = 0.0025) -> tuple[float, float]:
    """Effective duration and convexity from parallel curve bumps.

    Duration is per unit rate change (e.g. 5.0 means ~5% price change for a
    100bp parallel move); convexity is in the standard second-order units.
    """
    p0 = static_price(pool, curve)
    p_up = static_price(pool, curve.bumped(bump))
    p_dn = static_price(pool, curve.bumped(-bump))
    duration = (p_dn - p_up) / (2.0 * p0 * bump)
    convexity = (p_up + p_dn - 2.0 * p0) / (p0 * bump**2)
    return float(duration), float(convexity)


def scenario_prices(pool, curve, scenarios: dict[str, float]) -> dict[str, float]:
    """Static price under named parallel shifts (decimals), incl. the base."""
    out = {"base": static_price(pool, curve)}
    for name, shift in scenarios.items():
        out[name] = static_price(pool, curve.bumped(shift))
    return out
