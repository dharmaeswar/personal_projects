"""Market-microstructure analytics for NYSE-style trading data.

Per instrument-day measures built only from the trade tape in the
warehouse: VWAP, trade-price deviation from VWAP (an effective-spread
proxy, in basis points), buy/sell imbalance, intraday price dispersion
and the large-trade share. Days where deviation or imbalance is
extreme are flagged for the market-monitoring review, so a reviewer
starts from the days the tape itself says are unusual.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LARGE_TRADE_QTY = 40


def daily_microstructure(trades: pd.DataFrame) -> pd.DataFrame:
    """One row per instrument-day with microstructure measures."""
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "instrument", "trade_date", "vwap", "trades", "volume",
                "buy_qty", "sell_qty", "imbalance", "price_std_bps",
                "mean_abs_dev_bps", "max_abs_dev_bps", "large_trade_share",
            ]
        )
    t = trades.copy()
    t["notional"] = t["price"] * t["quantity"]
    t["dev_bps"] = 0.0
    grouped = t.groupby(["instrument", "trade_date"])
    vwap = grouped["notional"].sum() / grouped["quantity"].sum()
    rows = []
    for (inst, day), g in grouped:
        vw = float(vwap.loc[(inst, day)])
        dev = (g["price"] - vw) / vw * 10000
        buy = int(g.loc[g["side"] == "BUY", "quantity"].sum())
        sell = int(g.loc[g["side"] == "SELL", "quantity"].sum())
        vol = buy + sell
        rows.append(
            {
                "instrument": inst,
                "trade_date": day,
                "vwap": round(vw, 2),
                "trades": int(len(g)),
                "volume": vol,
                "buy_qty": buy,
                "sell_qty": sell,
                "imbalance": round((buy - sell) / vol, 4) if vol else 0.0,
                "price_std_bps": round(float(g["price"].std(ddof=0) / vw * 10000), 2)
                if len(g) > 1 else 0.0,
                "mean_abs_dev_bps": round(float(dev.abs().mean()), 2),
                "max_abs_dev_bps": round(float(dev.abs().max()), 2),
                "large_trade_share": round(
                    float(g.loc[g["quantity"] >= LARGE_TRADE_QTY, "quantity"].sum() / vol),
                    4,
                )
                if vol else 0.0,
            }
        )
    out = pd.DataFrame(rows).sort_values(["instrument", "trade_date"])
    return out.reset_index(drop=True)


def flag_microstructure_days(
    ms: pd.DataFrame,
    dev_threshold_bps: float = 25.0,
    imbalance_threshold: float = 0.25,
) -> pd.DataFrame:
    """Instrument-days whose tape looks unusual, with a plain reason.

    Defaults are set from the seeded demo tape (seed 42, 20 days):
    ordinary days peak at 10-17 bps from VWAP, while 12 of 120 days
    exceed 25 bps (the largest, 90 bps, is a planted close-marking
    trade); buy/sell imbalance tops out at 0.29, so 0.25 marks the
    tail. Thresholds are parameters, not hard-coded facts.
    """
    if ms.empty:
        return ms.copy()
    flagged = ms[
        (ms["max_abs_dev_bps"] >= dev_threshold_bps)
        | (ms["imbalance"].abs() >= imbalance_threshold)
    ].copy()
    reasons = []
    for _, r in flagged.iterrows():
        why = []
        if r["max_abs_dev_bps"] >= dev_threshold_bps:
            why.append(f"max price deviation {r['max_abs_dev_bps']:.1f} bps from VWAP")
        if abs(r["imbalance"]) >= imbalance_threshold:
            side = "buy" if r["imbalance"] > 0 else "sell"
            why.append(f"{side}-side imbalance {abs(r['imbalance']):.2f}")
        reasons.append("; ".join(why))
    flagged["reason"] = reasons
    return flagged.reset_index(drop=True)


def microstructure_summary(ms: pd.DataFrame) -> dict:
    """JSON-serialisable summary: medians and the flagged-day count."""
    if ms.empty:
        return {"instrument_days": 0, "flagged_days": 0}
    flagged = flag_microstructure_days(ms)
    return {
        "instrument_days": int(len(ms)),
        "median_mean_abs_dev_bps": round(float(ms["mean_abs_dev_bps"].median()), 2),
        "median_abs_imbalance": round(float(ms["imbalance"].abs().median()), 4),
        "median_large_trade_share": round(float(ms["large_trade_share"].median()), 4),
        "flagged_days": int(len(flagged)),
    }
