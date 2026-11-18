"""Medallion pipeline: bronze -> silver -> gold, with a Delta-style log.

Silver keeps only rows that pass every quality check; every rejected row
goes to a quarantine table with the reason it failed, so nothing is dropped
silently. Each table write appends a versioned entry to ``_delta_log.json``
in the table directory (operation, rows added, rows removed).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .checks import (
    MAX_ORDER_DATE,
    MIN_ORDER_DATE,
    check_completeness,
    check_ranges,
    check_referential_integrity,
    check_totals,
    check_uniqueness,
)
from .schema import GOLD_SCHEMA, ORDERS_SCHEMA, cast_to_schema


def _log_path(table_dir: Path) -> Path:
    return table_dir / "_delta_log.json"


def read_log(table_dir: Path) -> list[dict]:
    """Return the Delta-style transaction log for a table (empty if none)."""
    path = _log_path(table_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _append_log(table_dir: Path, operation: str, rows_added: int, rows_removed: int) -> dict:
    entries = read_log(table_dir)
    entry = {
        "version": len(entries) + 1,
        "operation": operation,
        "rows_added": rows_added,
        "rows_removed": rows_removed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    table_dir.mkdir(parents=True, exist_ok=True)
    _log_path(table_dir).write_text(json.dumps(entries, indent=2))
    return entry


def write_table(df: pd.DataFrame, table_dir: Path, operation: str) -> dict:
    """Write ``df`` as Parquet and append a Delta-style log entry."""
    table_dir.mkdir(parents=True, exist_ok=True)
    previous = 0
    data_file = table_dir / "data.parquet"
    if data_file.exists():
        previous = len(pd.read_parquet(data_file))
    df.to_parquet(data_file, index=False)
    return _append_log(
        table_dir,
        operation,
        rows_added=len(df),
        rows_removed=previous,
    )


def read_table(table_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(table_dir / "data.parquet")


def _flag_bad_rows(
    orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame
) -> tuple[pd.Series, dict[int, list[str]]]:
    """Return a boolean mask of rows failing any quality check, plus reasons."""
    reasons: dict[int, list[str]] = {}
    checks = [
        ("null key", check_completeness(orders, ["customer_id", "product_id"])),
        ("duplicate order_id", check_uniqueness(orders, "order_id")),
        ("quantity out of range", check_ranges(orders, "quantity", low=1)),
        ("unit_price out of range", check_ranges(orders, "unit_price", low=0)),
        (
            "order_date out of range",
            check_ranges(orders, "order_date", low=MIN_ORDER_DATE, high=MAX_ORDER_DATE),
        ),
        (
            "unknown customer_id",
            check_referential_integrity(orders, "customer_id", customers, "customer_id"),
        ),
        (
            "unknown product_id",
            check_referential_integrity(orders, "product_id", products, "product_id"),
        ),
        ("wrong total_amount", check_totals(orders)),
    ]
    for label, result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(label)
    mask = pd.Series(False, index=orders.index)
    for row in reasons:
        mask.loc[row] = True
    return mask, reasons


def build_silver(
    bronze_orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean bronze orders into silver + quarantine.

    Returns (silver_orders, quarantine). Silver is deduplicated, typed to
    the orders schema, and holds only rows that pass every check. Quarantine
    holds the rejected rows with a ``quarantine_reason`` column.
    """
    mask, reasons = _flag_bad_rows(bronze_orders, customers, products)
    quarantine = bronze_orders.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = bronze_orders.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["order_id"], keep="first")
    silver = cast_to_schema(silver, ORDERS_SCHEMA)
    silver = silver.reset_index(drop=True)
    quarantine = quarantine.reset_index(drop=True)
    return silver, quarantine


def build_gold(silver_orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Aggregate silver orders into daily revenue by category and region."""
    merged = silver_orders.merge(
        products[["product_id", "category"]], on="product_id", how="left"
    )
    merged["order_day"] = merged["order_date"].dt.normalize()
    gold = (
        merged.groupby(["order_day", "category", "region"], as_index=False)
        .agg(order_count=("order_id", "count"), total_revenue=("total_amount", "sum"))
        .rename(columns={"order_day": "order_date"})
    )
    gold["total_revenue"] = gold["total_revenue"].round(2)
    gold = cast_to_schema(gold, GOLD_SCHEMA)
    return gold.sort_values(["order_date", "category", "region"]).reset_index(drop=True)
