"""Performance attribution: expected vs realised return for a municipal portfolio.

When a portfolio under- or out-performs its expected return, the first
question is whether the gap is explained by market and economic drivers
(rates, curve shape, spreads, sector moves) or whether it is an unexplained
residual — which points at a data or model issue instead (a stale price, a
wrong benchmark mapping, a broken accrual). This module decomposes the gap
so the two cases are told apart with a number, not a hunch.

All figures are in percent (1.20 = 1.20%). All data handled here is
synthetic and seeded in the demo. No real issuer, CUSIP, or market data
appears anywhere in this project.
"""


def attribute_performance(expected_return_pct, realized_return_pct,
                         drivers, tolerance_pct=0.10):
    """Decompose the gap between expected and realised return.

    ``drivers`` is a list of ``{"name": ..., "contribution_pct": ...}``
    rows — the market/economic drivers (rates, curve, spread, sector,
    leverage/funding) and how much each contributed to the realised
    return. Returns a dict with the total gap, the explained part, the
    unexplained residual, and a verdict:

    - ``MARKET-DRIVEN`` when the unexplained residual is within
      ``tolerance_pct`` (default 10bp): the market explains the gap.
    - ``DATA/MODEL ISSUE - INVESTIGATE`` when it is not: the gap is
      bigger than the market drivers can explain, so the data or the
      model is the prime suspect.
    """
    explained = round(sum(d["contribution_pct"] for d in drivers), 4)
    gap = round(realized_return_pct - expected_return_pct, 4)
    unexplained = round(gap - explained, 4)
    return {
        "expected_return_pct": expected_return_pct,
        "realized_return_pct": realized_return_pct,
        "gap_pct": gap,
        "explained_pct": explained,
        "unexplained_pct": unexplained,
        "drivers": [{"name": d["name"],
                     "contribution_pct": d["contribution_pct"]}
                    for d in drivers],
        "verdict": ("MARKET-DRIVEN" if abs(unexplained) <= tolerance_pct
                    else "DATA/MODEL ISSUE - INVESTIGATE"),
    }


def performance_bridge(expected_return_pct, realized_return_pct, drivers,
                       tolerance_pct=0.10):
    """A readable, ordered walk from expected to realised return.

    Returns a list of ``(label, cumulative_pct)`` rows: the expected
    return, each driver applied in turn, and the realised return, plus
    the attribution verdict as the final row. A bridge whose last driver
    step lands far from the realised return is the visual form of the
    unexplained residual.
    """
    result = attribute_performance(expected_return_pct, realized_return_pct,
                                  drivers, tolerance_pct)
    rows = [("Expected return", expected_return_pct)]
    running = expected_return_pct
    for driver in drivers:
        running = round(running + driver["contribution_pct"], 4)
        rows.append((driver["name"], running))
    rows.append(("Unexplained residual", round(running + result["unexplained_pct"], 4)))
    rows.append(("Realised return", realized_return_pct))
    return {"bridge": rows, "verdict": result["verdict"],
            "unexplained_pct": result["unexplained_pct"]}
