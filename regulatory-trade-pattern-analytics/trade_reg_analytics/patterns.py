"""Trade-pattern detectors for market-regulation review.

Each detector returns a DataFrame of findings with a severity score
(0-100) and a plain-language reason, so a reviewer can triage before
opening the underlying orders. Detectors are rule-based and
transparent: no black-box model, every flag cites the orders behind it.
"""

from __future__ import annotations

import pandas as pd

WASH_MIN_QTY = 10
SPOOF_MIN_ORDERS = 5
SPOOF_MAX_CANCEL_SECONDS = 10.0
SPOOF_MIN_QTY = 100
CLOSE_WINDOW_MINUTES = 15
CONCENTRATION_THRESHOLD = 0.35


def _severity(count: int, cap: int = 10) -> int:
    return int(min(100, 40 + 60 * count / cap))


def detect_wash_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Same account buying and selling the same instrument, same day,
    in equal quantity at the same price — the classic wash-trade
    footprint. Exact quantity-and-price pairs are required: ordinary
    two-way trading almost never prints identical size and price on
    both sides of the same account."""
    rows = []
    for (acct, inst, day), grp in trades.groupby(["account", "instrument", "trade_date"]):
        buys = grp[grp["side"] == "BUY"]
        sells = grp[grp["side"] == "SELL"]
        if buys.empty or sells.empty:
            continue
        buy_pairs = buys.groupby(["quantity", "price"]).size().rename("buy_n")
        sell_pairs = sells.groupby(["quantity", "price"]).size().rename("sell_n")
        paired = buy_pairs.to_frame().join(sell_pairs, how="inner")
        if paired.empty:
            continue
        matched = 0
        for (qty, _price), r in paired.iterrows():
            matched += int(qty) * int(min(r["buy_n"], r["sell_n"]))
        if matched >= WASH_MIN_QTY:
            rows.append(
                {
                    "pattern": "wash_trade",
                    "account": acct,
                    "instrument": inst,
                    "trade_date": day,
                    "matched_quantity": matched,
                    "buy_quantity": int(buys["quantity"].sum()),
                    "sell_quantity": int(sells["quantity"].sum()),
                    "severity": _severity(matched, 50),
                    "reason": (
                        f"Account bought and sold {inst} on {day} in identical "
                        f"size-and-price pairs totalling {matched} contracts."
                    ),
                }
            )
    return pd.DataFrame(rows)


def detect_spoofing(orders: pd.DataFrame) -> pd.DataFrame:
    """Clusters of large orders cancelled within seconds — layering /
    spoofing behaviour that can mislead other participants."""
    cancelled = orders[
        (orders["status"] == "CANCELLED")
        & (orders["cancel_seconds"].notna())
        & (orders["cancel_seconds"] <= SPOOF_MAX_CANCEL_SECONDS)
        & (orders["quantity"] >= SPOOF_MIN_QTY)
    ]
    rows = []
    for (acct, inst, day, side), grp in cancelled.groupby(
        ["account", "instrument", "trade_date", "side"]
    ):
        if len(grp) >= SPOOF_MIN_ORDERS:
            rows.append(
                {
                    "pattern": "spoofing",
                    "account": acct,
                    "instrument": inst,
                    "trade_date": day,
                    "orders_cancelled": int(len(grp)),
                    "total_quantity": int(grp["quantity"].sum()),
                    "avg_cancel_seconds": round(float(grp["cancel_seconds"].mean()), 2),
                    "severity": _severity(len(grp), 12),
                    "reason": (
                        f"{len(grp)} large {side} orders in {inst} cancelled within "
                        f"{SPOOF_MAX_CANCEL_SECONDS:g}s on {day}."
                    ),
                }
            )
    return pd.DataFrame(rows)


def detect_marking_the_close(trades: pd.DataFrame) -> pd.DataFrame:
    """Trades in the last minutes of the session that move the price
    away from the day's volume-weighted average price (VWAP)."""
    rows = []
    for (inst, day), grp in trades.groupby(["instrument", "trade_date"]):
        vwap = float((grp["price"] * grp["quantity"]).sum() / grp["quantity"].sum())
        late = grp[grp["timestamp"].str.slice(11, 16) >= "15:45"]
        if late.empty:
            continue
        late_price = float(late["price"].mean())
        move_pct = abs(late_price - vwap) / vwap * 100
        if move_pct >= 0.2 and len(late) >= 3:
            rows.append(
                {
                    "pattern": "marking_the_close",
                    "account": ", ".join(sorted(late["account"].unique())[:3]),
                    "instrument": inst,
                    "trade_date": day,
                    "late_trades": int(len(late)),
                    "late_price": round(late_price, 2),
                    "vwap": round(vwap, 2),
                    "move_pct": round(move_pct, 3),
                    "severity": _severity(int(move_pct * 100), 50),
                    "reason": (
                        f"{len(late)} trades in the last 15 minutes priced "
                        f"{move_pct:.2f}% away from VWAP {vwap:.2f}."
                    ),
                }
            )
    return pd.DataFrame(rows)


def detect_position_concentration(positions: pd.DataFrame) -> pd.DataFrame:
    """One account holding a large share of open interest in an
    instrument on a day — a concentration flag for position review."""
    rows = []
    totals = positions.groupby(["instrument", "trade_date"])["net_quantity"].transform(
        lambda s: s.abs().sum()
    )
    enriched = positions.assign(total=totals)
    enriched = enriched[enriched["total"] > 0]
    enriched = enriched.assign(share=enriched["net_quantity"].abs() / enriched["total"])
    for _, r in enriched[enriched["share"] >= CONCENTRATION_THRESHOLD].iterrows():
        rows.append(
            {
                "pattern": "position_concentration",
                "account": r["account"],
                "instrument": r["instrument"],
                "trade_date": r["trade_date"],
                "net_quantity": int(r["net_quantity"]),
                "share_pct": round(float(r["share"]) * 100, 1),
                "severity": _severity(int(r["share"] * 100), 60),
                "reason": (
                    f"Account holds {float(r['share']) * 100:.1f}% of net open "
                    f"interest in {r['instrument']} on {r['trade_date']}."
                ),
            }
        )
    return pd.DataFrame(rows)


def run_all_detectors(
    orders: pd.DataFrame, trades: pd.DataFrame, positions: pd.DataFrame
) -> pd.DataFrame:
    """Run every detector and return one combined findings table."""
    frames = [
        detect_wash_trades(trades),
        detect_spoofing(orders),
        detect_marking_the_close(trades),
        detect_position_concentration(positions),
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(
            columns=["pattern", "account", "instrument", "trade_date", "severity", "reason"]
        )
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out.sort_values(["severity", "trade_date"], ascending=[False, True]).reset_index(drop=True)
