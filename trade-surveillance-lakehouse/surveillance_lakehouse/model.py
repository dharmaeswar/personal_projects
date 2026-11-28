"""Silver layer: cleaned, deduplicated dimensional model.

Grain statements (one row =):
- ``fact_order``: one order event (NEW or CANCEL) per order_id.
- ``fact_execution``: one fill per exec_id.
- ``fact_trade``: one market-trade print per trade_id.

Dedupe keeps the latest ``ingested_at`` row per business key, so a
re-sent feed never double-counts. Surrogate keys join facts to
``dim_instrument`` / ``dim_account``; every fact row must resolve to a
dimension row (referential integrity is checked, not assumed).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .generate import dim_account, dim_instrument
from .ingest import read_bronze


def _dedupe(df: pd.DataFrame, key: str) -> tuple[pd.DataFrame, int]:
    """Keep the latest ingested row per business key; return (kept, n_dupes)."""
    before = len(df)
    kept = (df.sort_values("ingested_at")
              .drop_duplicates(subset=[key], keep="last")
              .reset_index(drop=True))
    return kept, before - len(kept)


def build_silver(bronze_dir: Path, silver_dir: Path) -> dict:
    """Build dims + facts from bronze. Returns counts and DQ findings."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    dims = {}
    dims["dim_instrument"] = dim_instrument()
    dims["dim_instrument"].insert(0, "instrument_key",
                                  range(1, len(dims["dim_instrument"]) + 1))
    dims["dim_account"] = dim_account()
    dims["dim_account"].insert(0, "account_key",
                               range(1, len(dims["dim_account"]) + 1))
    for name, df in dims.items():
        df.to_parquet(silver_dir / f"{name}.parquet", index=False)

    inst_key = {s: i + 1 for i, s in enumerate(dims["dim_instrument"]["symbol"])}
    acct_key = {a: i + 1 for i, a in enumerate(dims["dim_account"]["account_id"])}

    report: dict = {"duplicates_removed": {}, "late_arrivals": {}}
    facts = {}

    orders = read_bronze("orders", bronze_dir)
    orders, n_dup = _dedupe(orders, "order_id")
    report["duplicates_removed"]["orders"] = n_dup
    orders["trade_date"] = pd.to_datetime(orders["trade_date"]).dt.date
    orders["is_late"] = (pd.to_datetime(orders["ingested_at"])
                         - pd.to_datetime(orders["order_ts"])
                         > pd.Timedelta(days=1))
    report["late_arrivals"]["orders"] = int(orders["is_late"].sum())
    fact_order = pd.DataFrame({
        "order_key": range(1, len(orders) + 1),
        "order_id": orders["order_id"],
        "account_key": orders["account_id"].map(acct_key),
        "instrument_key": orders["symbol"].map(inst_key),
        "side": orders["side"], "qty": orders["qty"],
        "limit_price": orders["limit_price"],
        "order_ts": pd.to_datetime(orders["order_ts"]),
        "event": orders["event"],
        "trade_date": orders["trade_date"],
        "is_late": orders["is_late"],
    })
    facts["fact_order"] = fact_order

    executions = read_bronze("executions", bronze_dir)
    executions, n_dup = _dedupe(executions, "exec_id")
    report["duplicates_removed"]["executions"] = n_dup
    executions["trade_date"] = pd.to_datetime(executions["trade_date"]).dt.date
    executions["is_late"] = (pd.to_datetime(executions["ingested_at"])
                             - pd.to_datetime(executions["exec_ts"])
                             > pd.Timedelta(days=1))
    report["late_arrivals"]["executions"] = int(executions["is_late"].sum())
    fact_execution = pd.DataFrame({
        "exec_key": range(1, len(executions) + 1),
        "exec_id": executions["exec_id"],
        "order_id": executions["order_id"],
        "instrument_key": executions["symbol"].map(inst_key),
        "qty": executions["qty"], "price": executions["price"],
        "exec_ts": pd.to_datetime(executions["exec_ts"]),
        "trade_date": executions["trade_date"],
        "is_late": executions["is_late"],
    })
    facts["fact_execution"] = fact_execution

    trades = read_bronze("trades", bronze_dir)
    trades, n_dup = _dedupe(trades, "trade_id")
    report["duplicates_removed"]["trades"] = n_dup
    trades["trade_date"] = pd.to_datetime(trades["trade_date"]).dt.date
    fact_trade = pd.DataFrame({
        "trade_key": range(1, len(trades) + 1),
        "trade_id": trades["trade_id"],
        "instrument_key": trades["symbol"].map(inst_key),
        "price": trades["price"], "qty": trades["qty"],
        "trade_ts": pd.to_datetime(trades["trade_ts"]),
        "trade_date": trades["trade_date"],
    })
    facts["fact_trade"] = fact_trade

    # Referential integrity: every fact key must resolve to a dimension.
    checks = {}
    checks["fact_order_account_fk"] = int(fact_order["account_key"].isna().sum())
    checks["fact_order_instrument_fk"] = int(
        fact_order["instrument_key"].isna().sum())
    checks["fact_execution_instrument_fk"] = int(
        fact_execution["instrument_key"].isna().sum())
    checks["fact_trade_instrument_fk"] = int(
        fact_trade["instrument_key"].isna().sum())
    # Executions must reference a known order.
    known_orders = set(fact_order["order_id"])
    checks["fact_execution_orphan_orders"] = int(
        (~fact_execution["order_id"].isin(known_orders)).sum())
    report["referential_integrity_violations"] = checks

    for name, df in facts.items():
        df.to_parquet(silver_dir / f"{name}.parquet", index=False)
    report["fact_rows"] = {name: len(df) for name, df in facts.items()}
    report["dim_rows"] = {name: len(df) for name, df in dims.items()}
    return report
