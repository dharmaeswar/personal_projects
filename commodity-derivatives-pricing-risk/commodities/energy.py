"""Energy derivatives: spark spreads and seasonal power forward curves.

A spark spread is the margin a gas-fired power plant earns: the power
price minus the gas cost of generating it, ``P - H * G``, where ``H``
is the plant heat rate in MMBtu per MWh (7.0 is a typical combined-
cycle value). A spark-spread call pays ``max(P - H*G - K, 0)`` — it is
the structured transaction a gas plant or a power trader buys to lock
in generation margin, and it is the payoff this module values by
Monte Carlo under correlated lognormal power and gas forwards.

Power forward curves are seasonal in a way oil curves are not: summer
air-conditioning load (July peak) and winter heating load (January)
lift prices, so the curve is built as a base price times a monthly
seasonal shape instead of a flat cost-of-carry line.

All prices here are synthetic and seeded; no real market data is
used, and nothing here is a claim about any real price, curve, or
return.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_HEAT_RATE = 7.0  # MMBtu per MWh, typical combined-cycle plant


def spark_spread(power_price: float, gas_price: float, heat_rate: float = DEFAULT_HEAT_RATE) -> float:
    """Generation margin in $/MWh: power price less gas cost per MWh."""
    if power_price <= 0 or gas_price <= 0 or heat_rate <= 0:
        raise ValueError("power_price, gas_price and heat_rate must be positive")
    return power_price - heat_rate * gas_price


def spark_spread_breakeven_gas(
    power_price: float, heat_rate: float = DEFAULT_HEAT_RATE, strike: float = 0.0
) -> float:
    """Gas price ($/MMBtu) at which the spread equals ``strike``.

    Above this gas price the plant's margin is below the strike; below
    it the plant is in the money. Solves ``P - H*G = K`` for ``G``.
    """
    if power_price <= 0 or heat_rate <= 0:
        raise ValueError("power_price and heat_rate must be positive")
    breakeven = (power_price - strike) / heat_rate
    if breakeven <= 0:
        raise ValueError("strike exceeds the power price: no positive breakeven gas price")
    return breakeven


def seasonal_power_forward_curve(
    base_price: float, months: int = 12, peak_month: int = 7, amplitude: float = 0.25
) -> pd.DataFrame:
    """Monthly power forward curve: base price times a seasonal shape.

    The shape is ``1 + amplitude * cos(2*pi*(month - peak_month)/12)``,
    so the curve peaks in ``peak_month`` (July by default, summer
    cooling load) and troughs six months later. ``amplitude`` is the
    fractional seasonal swing; 0.25 means the peak month runs 25%
    above the base price.
    """
    if base_price <= 0 or months <= 0:
        raise ValueError("base_price and months must be positive")
    if not 1 <= peak_month <= 12:
        raise ValueError("peak_month must be 1-12")
    if not 0 <= amplitude < 1:
        raise ValueError("amplitude must be in [0, 1)")
    rows = []
    for m in range(1, months + 1):
        shape = 1.0 + amplitude * math.cos(2.0 * math.pi * (m - peak_month) / 12.0)
        rows.append(
            {"month": m, "seasonal_factor": round(shape, 4), "forward_price": round(base_price * shape, 2)}
        )
    return pd.DataFrame(rows)


def spark_spread_call_mc(
    power_forward: float,
    gas_forward: float,
    heat_rate: float = DEFAULT_HEAT_RATE,
    strike: float = 0.0,
    T: float = 0.5,
    power_vol: float = 0.80,
    gas_vol: float = 0.65,
    correlation: float = 0.60,
    r: float = 0.045,
    n_paths: int = 20000,
    seed: int = 7,
) -> dict:
    """Monte Carlo value of a European spark-spread call.

    Payoff ``max(P_T - H*G_T - K, 0)`` at expiry, discounted at ``r``.
    Power and gas forwards are driftless lognormals under the
    risk-neutral measure (the futures-measure convention Black-76
    uses), with correlated Brownian shocks via a Cholesky factor.
    Returns the value, its Monte Carlo standard error, and the
    discounted intrinsic value (the no-volatility floor the value
    must sit above).
    """
    if power_forward <= 0 or gas_forward <= 0 or heat_rate <= 0:
        raise ValueError("forwards and heat_rate must be positive")
    if T <= 0 or power_vol < 0 or gas_vol < 0:
        raise ValueError("T must be positive and vols non-negative")
    if not -1.0 <= correlation <= 1.0:
        raise ValueError("correlation must be in [-1, 1]")
    rng = np.random.default_rng(seed)
    z1 = rng.standard_normal(n_paths)
    z2 = rng.standard_normal(n_paths)
    # Correlated second shock: z2' = rho*z1 + sqrt(1-rho^2)*z2.
    z2c = correlation * z1 + math.sqrt(max(0.0, 1.0 - correlation * correlation)) * z2
    sqrt_t = math.sqrt(T)
    p_t = power_forward * np.exp(-0.5 * power_vol**2 * T + power_vol * sqrt_t * z1)
    g_t = gas_forward * np.exp(-0.5 * gas_vol**2 * T + gas_vol * sqrt_t * z2c)
    payoff = np.maximum(p_t - heat_rate * g_t - strike, 0.0)
    disc = math.exp(-r * T)
    value = float(disc * payoff.mean())
    std_error = float(disc * payoff.std(ddof=1) / math.sqrt(n_paths))
    intrinsic = max(spark_spread(power_forward, gas_forward, heat_rate) - strike, 0.0)
    return {
        "value": round(value, 4),
        "std_error": round(std_error, 4),
        "discounted_intrinsic": round(disc * intrinsic, 4),
        "spread_now": round(spark_spread(power_forward, gas_forward, heat_rate), 2),
    }


def check_spark_spread_call_bounds(result: dict, power_forward: float, r: float, T: float) -> dict:
    """Validation: a spread call must clear its intrinsic floor and
    cannot be worth more than the discounted power leg itself."""
    value = result["value"]
    floor = result["discounted_intrinsic"]
    cap = math.exp(-r * T) * power_forward
    passed = floor - 1e-9 <= value <= cap + 1e-9
    return {
        "check": "spark-spread call within intrinsic floor and power-leg cap",
        "passed": bool(passed),
        "value": value,
        "floor": floor,
        "cap": round(cap, 4),
    }
