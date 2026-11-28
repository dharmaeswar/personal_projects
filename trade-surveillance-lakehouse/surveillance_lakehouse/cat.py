"""CAT report export.

Writes the gold ``cat_events`` rows as a pipe-delimited text file in the
shape of a Consolidated Audit Trail (CAT) order-event submission: one
row per firm order event, with the fields a CAT reporter files
(firm order id, event type, symbol, side, quantity, price, event
timestamp, account). This is a format demo on synthetic data — it is
not a real CAT filing and nothing here is submitted to any regulator.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CAT_COLUMNS = ["event_date", "firm_order_id", "event_type", "symbol",
               "side", "quantity", "price", "event_timestamp",
               "account_id"]

EVENT_TYPES = {"NEW": "MEOA", "CANCEL": "MEOC"}  # order accepted / cancelled


def export_cat(gold_dir: Path, out_path: Path) -> dict:
    """Write the CAT file. Returns row count and the output path."""
    events = pd.read_parquet(gold_dir / "cat_events.parquet")
    cat = pd.DataFrame({
        "event_date": pd.to_datetime(events["trade_date"]).dt.strftime("%Y%m%d"),
        "firm_order_id": events["firm_order_id"],
        "event_type": events["event"].map(EVENT_TYPES),
        "symbol": events["symbol"],
        "side": events["side"],
        "quantity": events["qty"],
        "price": events["price"].map(lambda p: f"{p:.2f}"),
        "event_timestamp": pd.to_datetime(events["event_ts"]).dt.strftime(
            "%Y-%m-%dT%H:%M:%S"),
        "account_id": events["account_id"],
    })
    if cat["event_type"].isna().any():
        raise ValueError("unmapped order event type in CAT export")
    if cat.isna().any().any():
        raise ValueError("null field in CAT export")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cat.to_csv(out_path, sep="|", index=False)
    return {"rows": len(cat), "path": str(out_path),
            "event_types": cat["event_type"].value_counts().to_dict()}
