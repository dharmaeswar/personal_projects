"""Statistical analysis for regulatory trade data.

Rolling volume and price statistics, z-scores and outlier flags used
to triage which days, instruments and accounts deserve a closer look
before the pattern detectors run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_volume(trades: pd.DataFrame) -> pd.DataFrame:
    """Total traded quantity and trade count per instrument and day."""
    return (
        trades.groupby(["instrument", "trade_date"], as_index=False)
        .agg(volume=("quantity", "sum"), trades=("trade_id", "count"))
        .sort_values(["instrument", "trade_date"])
    )


def add_zscores(daily: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Rolling mean/std z-score of daily volume within each instrument."""
    out = daily.copy()
    out["vol_mean"] = (
        out.groupby("instrument")["volume"]
        .transform(lambda s: s.rolling(window, min_periods=2).mean())
    )
    out["vol_std"] = (
        out.groupby("instrument")["volume"]
        .transform(lambda s: s.rolling(window, min_periods=2).std())
    )
    out["volume_z"] = (out["volume"] - out["vol_mean"]) / out["vol_std"].replace(0, np.nan)
    out["volume_z"] = out["volume_z"].fillna(0.0)
    return out


def flag_outlier_days(daily: pd.DataFrame, threshold: float = 2.0) -> pd.DataFrame:
    """Days whose volume z-score exceeds the threshold."""
    scored = add_zscores(daily)
    return scored[scored["volume_z"].abs() >= threshold].copy()


def account_volume_share(trades: pd.DataFrame) -> pd.DataFrame:
    """Each account's share of total volume per instrument and day."""
    totals = trades.groupby(["instrument", "trade_date"])["quantity"].transform("sum")
    by_acct = (
        trades.assign(share=trades["quantity"] / totals)
        .groupby(["instrument", "trade_date", "account"], as_index=False)
        .agg(volume=("quantity", "sum"), share=("share", "sum"))
    )
    return by_acct.sort_values("share", ascending=False)


def price_move_stats(trades: pd.DataFrame) -> pd.DataFrame:
    """Per-instrument daily close-to-close returns and their z-scores."""
    daily_close = (
        trades.sort_values("timestamp")
        .groupby(["instrument", "trade_date"], as_index=False)
        .agg(close=("price", "last"))
    )
    daily_close["ret"] = daily_close.groupby("instrument")["close"].pct_change()
    daily_close["ret_z"] = daily_close.groupby("instrument")["ret"].transform(
        lambda s: (s - s.mean()) / s.std()
    )
    return daily_close
