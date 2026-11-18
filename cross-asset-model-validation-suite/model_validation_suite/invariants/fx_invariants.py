"""FX invariants.

Context keys: ``spot``, ``domestic_rate``, ``foreign_rate``, ``vol``,
``tenor``, ``strikes``, ``tolerances``.
"""

from __future__ import annotations

import math

from ..models.fx import fx_forward, garman_kohlhagen
from ..models.rates import DiscountCurve
from .framework import Outcome, invariant


@invariant("fx", "forward_interest_rate_parity",
           "Forward from rate differential equals spot x DF_foreign / DF_domestic.")
def forward_parity(ctx: dict) -> Outcome:
    tol = ctx["tolerances"].get("parity", 1e-9)
    s, rd, rf, t = ctx["spot"], ctx["domestic_rate"], ctx["foreign_rate"], ctx["tenor"]
    fwd_model = fx_forward(s, rd, rf, t)
    curve_d = DiscountCurve([t], [rd])
    curve_f = DiscountCurve([t], [rf])
    fwd_from_curves = s * curve_f.discount(t) / curve_d.discount(t)
    err = abs(fwd_model - fwd_from_curves)
    return Outcome(err <= tol, err, tol,
                   f"|F_model - S*DF_f/DF_d| = {err:.3e} (F={fwd_model:.6f})")


@invariant("fx", "fx_put_call_parity",
           "Garman-Kohlhagen put-call parity: C - P = S e^{-rf T} - K e^{-rd T}.")
def fx_put_call_parity(ctx: dict) -> Outcome:
    tol = ctx["tolerances"].get("parity", 1e-9)
    s, rd, rf = ctx["spot"], ctx["domestic_rate"], ctx["foreign_rate"]
    vol, t = ctx["vol"], ctx["tenor"]
    df_d = math.exp(-rd * t)
    df_f = math.exp(-rf * t)
    worst = 0.0
    for k in ctx["strikes"]:
        call = garman_kohlhagen(s, k, rd, rf, vol, t, is_call=True)
        put = garman_kohlhagen(s, k, rd, rf, vol, t, is_call=False)
        worst = max(worst, abs((call - put) - (s * df_f - k * df_d)))
    return Outcome(worst <= tol, worst, tol,
                   f"max parity error over {len(ctx['strikes'])} strikes: {worst:.3e}")


@invariant("fx", "forward_monotonic_in_domestic_rate",
           "FX forward strictly increases with the domestic interest rate.")
def forward_monotonic(ctx: dict) -> Outcome:
    s, rd, rf, t = ctx["spot"], ctx["domestic_rate"], ctx["foreign_rate"], ctx["tenor"]
    f_low = fx_forward(s, rd, rf, t)
    f_high = fx_forward(s, rd + 0.005, rf, t)
    diff = f_high - f_low
    return Outcome(diff > 0.0, diff, 0.0,
                   f"F(rd+0.5%) - F(rd) = {diff:.6f}")
