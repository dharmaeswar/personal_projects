"""FX models: outright forwards (interest-rate parity) and Garman-Kohlhagen
option pricing. Rates are continuously compounded; times in years.
"""

from __future__ import annotations

import math

from .equity import norm_cdf


def fx_forward(spot: float, domestic_rate: float, foreign_rate: float,
               tenor: float) -> float:
    """FX outright forward from covered interest-rate parity.

    F = S * exp((r_domestic - r_foreign) * T), with S quoted as domestic
    currency per unit of foreign currency.
    """
    return spot * math.exp((domestic_rate - foreign_rate) * tenor)


def garman_kohlhagen(spot: float, strike: float, domestic_rate: float,
                     foreign_rate: float, vol: float, tenor: float,
                     is_call: bool = True) -> float:
    """Garman-Kohlhagen price of a European FX option.

    Black-Scholes with the foreign rate acting as a continuous yield:
        d1 = [ln(S/K) + (rd - rf + sigma^2/2) T] / (sigma sqrt(T))
        call = S e^{-rf T} N(d1) - K e^{-rd T} N(d2)
        put  = K e^{-rd T} N(-d2) - S e^{-rf T} N(-d1)
    """
    if tenor <= 0 or vol <= 0:
        # Degenerate expiry/vol: intrinsic value against the forward.
        fwd = fx_forward(spot, domestic_rate, foreign_rate, max(tenor, 0.0))
        disc = math.exp(-domestic_rate * max(tenor, 0.0))
        intrinsic = max(fwd - strike, 0.0) if is_call else max(strike - fwd, 0.0)
        return disc * intrinsic
    sqrt_t = math.sqrt(tenor)
    d1 = (math.log(spot / strike)
          + (domestic_rate - foreign_rate + 0.5 * vol * vol) * tenor) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    df_d = math.exp(-domestic_rate * tenor)
    df_f = math.exp(-foreign_rate * tenor)
    if is_call:
        return spot * df_f * norm_cdf(d1) - strike * df_d * norm_cdf(d2)
    return strike * df_d * norm_cdf(-d2) - spot * df_f * norm_cdf(-d1)
