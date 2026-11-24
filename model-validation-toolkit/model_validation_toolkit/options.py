"""Options-pricing model validation: Black-Scholes pricing, implied volatility,
put-call parity, Greeks, and book-level validation against observed marks.

Pure standard library. All functions take plain numbers / dicts and return plain
dicts, so results are easy to log into a validation document. Prices use the
Black-Scholes model under constant volatility and rates; the module validates a
pricing model against observed marks, it does not claim the model is correct.
"""
import math
from typing import Dict, List, Sequence


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _check_inputs(spot: float, strike: float, rate: float,
                  time_to_expiry: float, vol: float) -> None:
    if spot <= 0:
        raise ValueError("spot must be positive")
    if strike <= 0:
        raise ValueError("strike must be positive")
    if time_to_expiry <= 0:
        raise ValueError("time_to_expiry must be positive")
    if vol <= 0:
        raise ValueError("vol must be positive")


def black_scholes_price(spot: float, strike: float, rate: float,
                        time_to_expiry: float, vol: float,
                        option_type: str = "call") -> float:
    """Black-Scholes price of a European call or put.

    option_type must be "call" or "put".
    """
    _check_inputs(spot, strike, rate, time_to_expiry, vol)
    if option_type not in ("call", "put"):
        raise ValueError('option_type must be "call" or "put"')
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_to_expiry) \
        / (vol * math.sqrt(time_to_expiry))
    d2 = d1 - vol * math.sqrt(time_to_expiry)
    disc = math.exp(-rate * time_to_expiry)
    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
    return strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def implied_volatility(market_price: float, spot: float, strike: float,
                       rate: float, time_to_expiry: float,
                       option_type: str = "call",
                       tol: float = 1e-6) -> float:
    """Implied volatility from an observed market price, by bisection.

    Raises ValueError when the price is outside the no-arbitrage bounds for
    the contract (below intrinsic value or above the maximum possible price).
    """
    _check_inputs(spot, strike, rate, time_to_expiry, 0.2)
    if option_type not in ("call", "put"):
        raise ValueError('option_type must be "call" or "put"')
    disc = math.exp(-rate * time_to_expiry)
    if option_type == "call":
        intrinsic = max(spot - strike * disc, 0.0)
        ceiling = spot
    else:
        intrinsic = max(strike * disc - spot, 0.0)
        ceiling = strike * disc
    if market_price < intrinsic - 1e-9 or market_price > ceiling + 1e-9:
        raise ValueError("market price outside no-arbitrage bounds")
    lo, hi = 1e-6, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        price = black_scholes_price(spot, strike, rate, time_to_expiry, mid,
                                     option_type)
        if abs(price - market_price) < tol:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def put_call_parity_gap(call_price: float, put_price: float, spot: float,
                        strike: float, rate: float,
                        time_to_expiry: float) -> float:
    """C - P - (S - K * exp(-rT)). Zero when put-call parity holds exactly."""
    if time_to_expiry <= 0:
        raise ValueError("time_to_expiry must be positive")
    return call_price - put_price - (spot - strike * math.exp(-rate * time_to_expiry))


def greeks(spot: float, strike: float, rate: float, time_to_expiry: float,
           vol: float, option_type: str = "call") -> Dict[str, float]:
    """Black-Scholes Greeks: delta, gamma, vega, theta (per year), rho."""
    _check_inputs(spot, strike, rate, time_to_expiry, vol)
    if option_type not in ("call", "put"):
        raise ValueError('option_type must be "call" or "put"')
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_to_expiry) \
        / (vol * math.sqrt(time_to_expiry))
    d2 = d1 - vol * math.sqrt(time_to_expiry)
    disc = math.exp(-rate * time_to_expiry)
    sqrt_t = math.sqrt(time_to_expiry)
    gamma = _norm_pdf(d1) / (spot * vol * sqrt_t)
    vega = spot * _norm_pdf(d1) * sqrt_t
    if option_type == "call":
        delta = _norm_cdf(d1)
        theta = (-spot * _norm_pdf(d1) * vol / (2 * sqrt_t)
                 - rate * strike * disc * _norm_cdf(d2))
        rho = strike * time_to_expiry * disc * _norm_cdf(d2)
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-spot * _norm_pdf(d1) * vol / (2 * sqrt_t)
                 + rate * strike * disc * _norm_cdf(-d2))
        rho = -strike * time_to_expiry * disc * _norm_cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "rho": rho}


def validate_option_book(contracts: Sequence[Dict], tolerance: float = 0.05,
                         parity_tolerance: float = 0.01) -> Dict:
    """Validate a book of option contracts against Black-Scholes model prices.

    Each contract is a dict with keys: spot, strike, rate, time_to_expiry,
    vol, option_type ("call"/"put"), market_price. Returns per-contract
    results (model price, absolute and relative error, breach flag,
    implied volatility, put-call parity gap where a matching pair exists)
    plus a summary with breach counts and the worst offenders.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    results = []
    for i, c in enumerate(contracts):
        model = black_scholes_price(c["spot"], c["strike"], c["rate"],
                                    c["time_to_expiry"], c["vol"],
                                    c.get("option_type", "call"))
        market = float(c["market_price"])
        error = model - market
        rel = abs(error) / market if market else float("inf")
        iv = implied_volatility(market, c["spot"], c["strike"], c["rate"],
                                c["time_to_expiry"], c.get("option_type", "call"))
        results.append({
            "index": i,
            "option_type": c.get("option_type", "call"),
            "strike": c["strike"],
            "time_to_expiry": c["time_to_expiry"],
            "model_price": round(model, 4),
            "market_price": round(market, 4),
            "error": round(error, 4),
            "relative_error": round(rel, 4),
            "breach": rel > tolerance,
            "implied_volatility": round(iv, 4),
            "parity_gap": None,
        })
    # Put-call parity for call/put pairs sharing spot, strike, rate, expiry.
    for r in results:
        if r["option_type"] != "call":
            continue
        c = contracts[r["index"]]
        for other in results:
            o = contracts[other["index"]]
            if (other["option_type"] == "put"
                    and o["strike"] == c["strike"]
                    and o["time_to_expiry"] == c["time_to_expiry"]
                    and o["spot"] == c["spot"] and o["rate"] == c["rate"]):
                gap = put_call_parity_gap(r["market_price"], other["market_price"],
                                          c["spot"], c["strike"], c["rate"],
                                          c["time_to_expiry"])
                r["parity_gap"] = round(gap, 4)
                other["parity_gap"] = round(gap, 4)
    breaches = [r for r in results if r["breach"]]
    parity_breaches = [r for r in results
                       if r["parity_gap"] is not None
                       and abs(r["parity_gap"]) > parity_tolerance]
    worst = max(results, key=lambda r: r["relative_error"]) if results else None
    return {
        "contracts": len(results),
        "breaches": len(breaches),
        "parity_breaches": len(parity_breaches),
        "worst_relative_error": worst["relative_error"] if worst else None,
        "worst_index": worst["index"] if worst else None,
        "results": results,
    }
