"""Portfolio risk: historical and parametric VaR / expected shortfall,
and Greeks aggregation for a small book of options.

VaR is reported as a positive loss number (the loss that is exceeded with
probability ``alpha``). Pure standard library.
"""

import math


def _sorted_losses(returns):
    if not returns:
        raise ValueError("returns must be non-empty")
    return sorted(-r for r in returns)


def historical_var(returns, alpha: float = 0.05) -> float:
    """Historical VaR at tail probability ``alpha`` (e.g. 0.05 = 95% VaR).

    Losses are sorted ascending; the VaR is the loss at the (1 - alpha)
    quantile, i.e. counted down from the worst loss.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    losses = _sorted_losses(returns)
    n = len(losses)
    idx = n - math.ceil(alpha * n)
    return losses[max(idx, 0)]


def historical_es(returns, alpha: float = 0.05) -> float:
    """Historical expected shortfall: mean loss beyond the VaR threshold."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    losses = _sorted_losses(returns)
    n = len(losses)
    k = max(math.ceil(alpha * n), 1)
    tail = losses[n - k:]
    return sum(tail) / len(tail)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""
    if not 0 < p < 1:
        raise ValueError("p must be between 0 and 1")
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285984469534e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def parametric_var(returns, alpha: float = 0.05) -> float:
    """Normal (delta-normal) VaR from the sample mean and volatility."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not returns:
        raise ValueError("returns must be non-empty")
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1 if n > 1 else 1)
    return -(mean + _norm_ppf(alpha) * math.sqrt(var))


def aggregate_greeks(positions) -> dict:
    """Sum Greeks over a book. ``positions``: list of (quantity, greeks-dict).

    Each greeks dict carries delta/gamma/vega/theta/rho for one option.
    """
    total = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    for qty, greeks in positions:
        for key in total:
            if key not in greeks:
                raise ValueError(f"greeks dict is missing {key}")
            total[key] += qty * greeks[key]
    return total
