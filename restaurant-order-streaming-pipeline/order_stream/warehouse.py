"""Warehouse writes: partitioned Parquet + star schema + SCD2 dimensions.

Layout mirrors a cloud data lake / warehouse the way the posting describes
it: fact tables partitioned by event date and restaurant (the S3 / GCS
object layout), with a star schema on top (the Redshift / BigQuery model).
``write_fact`` appends a Parquet partition; ``dim_menu_item`` is a
slowly-changing dimension type 2, so a menu price change keeps history.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

from .events import MENU, RESTAURANTS, OrderEvent


def fact_rows(events: list[OrderEvent]) -> pd.DataFrame:
    """Build the fact_orders star-schema rows from clean events."""
    rows = []
    for e in events:
        name, _ = MENU[e.menu_code]
        market, region = RESTAURANTS[e.restaurant_id][1], RESTAURANTS[e.restaurant_id][2]
        rows.append(
            {
                "order_id": e.order_id,
                "event_date": e.event_time.date().isoformat(),
                "event_time": e.event_time.isoformat(),
                "restaurant_id": e.restaurant_id,
                "market": market,
                "region": region,
                "channel": e.channel,
                "menu_code": e.menu_code,
                "menu_item": name,
                "quantity": e.quantity,
                "unit_price": e.unit_price,
                "total_amount": e.total_amount,
            }
        )
    return pd.DataFrame(rows)


def write_fact(df: pd.DataFrame, warehouse_dir: str) -> list[str]:
    """Append fact rows as Parquet partitions ``event_date=.../restaurant_id=...``.

    Returns the list of partition files written. Empty input writes nothing.
    """
    written: list[str] = []
    if df.empty:
        return written
    for (event_date, restaurant_id), part in df.groupby(["event_date", "restaurant_id"]):
        path = os.path.join(
            warehouse_dir, "fact_orders",
            f"event_date={event_date}", f"restaurant_id={restaurant_id}",
        )
        os.makedirs(path, exist_ok=True)
        file_path = os.path.join(path, f"part-{len(os.listdir(path)):04d}.parquet")
        part.drop(columns=["event_date", "restaurant_id"]).to_parquet(file_path, index=False)
        written.append(file_path)
    return written


def dim_restaurant() -> pd.DataFrame:
    """Dimension table for restaurants, from the master-data table."""
    return pd.DataFrame(
        [
            {"restaurant_id": rid, "name": name, "market": market, "region": region}
            for rid, (name, market, region) in RESTAURANTS.items()
        ]
    )


def dim_menu_item_scd2(price_changes: list[tuple[str, float, datetime]] | None = None) -> pd.DataFrame:
    """Menu-item dimension with SCD2 history.

    Each row carries ``valid_from`` / ``valid_to``; the current row has
    ``valid_to`` NULL. ``price_changes`` is a list of (menu_code, new_price,
    effective_from) applied on top of the seeded prices.
    """
    rows = []
    for code, (name, price) in MENU.items():
        rows.append(
            {
                "menu_code": code, "menu_item": name, "unit_price": price,
                "valid_from": "2026-01-01", "valid_to": None, "is_current": True,
            }
        )
    for code, new_price, effective in price_changes or []:
        name, _ = MENU[code]
        for row in rows:
            if row["menu_code"] == code and row["is_current"]:
                row["valid_to"] = effective.date().isoformat()
                row["is_current"] = False
        rows.append(
            {
                "menu_code": code, "menu_item": name, "unit_price": new_price,
                "valid_from": effective.date().isoformat(), "valid_to": None,
                "is_current": True,
            }
        )
    return pd.DataFrame(rows)
