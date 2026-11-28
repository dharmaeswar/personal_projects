"""Gold layer: surveillance foundations + data-quality report.

- ``account_day_features``: per account / day / symbol aggregates the
  surveillance models consume — order and execution counts, notional,
  cancel rate, and a wash-trade candidate flag (matched buy and sell
  size in the same symbol on the same day by the same account).
- ``cat_events``: CAT-ready order-event rows (see cat.py for the export).
- ``dq_report``: completeness, uniqueness and silver->gold
  reconciliation, so a reviewer can check the gold layer instead of
  trusting it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_gold(silver_dir: Path, gold_dir: Path) -> dict:
    """Build gold tables from silver. Returns the DQ report dict."""
    gold_dir.mkdir(parents=True, exist_ok=True)
    orders = pd.read_parquet(silver_dir / "fact_order.parquet")
    executions = pd.read_parquet(silver_dir / "fact_execution.parquet")
    trades = pd.read_parquet(silver_dir / "fact_trade.parquet")
    instruments = pd.read_parquet(silver_dir / "dim_instrument.parquet")
    accounts = pd.read_parquet(silver_dir / "dim_account.parquet")
    sym = dict(zip(instruments["instrument_key"], instruments["symbol"]))
    acct = dict(zip(accounts["account_key"], accounts["account_id"]))

    orders = orders.assign(symbol=orders["instrument_key"].map(sym),
                           account_id=orders["account_key"].map(acct))
    executions = executions.assign(
        symbol=executions["instrument_key"].map(sym))
    trades = trades.assign(symbol=trades["instrument_key"].map(sym))

    # --- account-day-symbol features ---
    new_orders = orders[orders["event"] == "NEW"].copy()
    new_orders["notional"] = new_orders["qty"] * new_orders["limit_price"]
    buys = new_orders[new_orders["side"] == "BUY"].groupby(
        ["account_id", "trade_date", "symbol"])["qty"].sum().rename("buy_qty")
    sells = new_orders[new_orders["side"] == "SELL"].groupby(
        ["account_id", "trade_date", "symbol"])["qty"].sum().rename("sell_qty")
    feats = (new_orders.groupby(["account_id", "trade_date", "symbol"])
             .agg(order_count=("order_id", "count"),
                  total_qty=("qty", "sum"),
                  notional=("notional", "sum"))
             .reset_index())
    cancels = (orders[orders["event"] == "CANCEL"]
               .groupby(["account_id", "trade_date", "symbol"]).size()
               .rename("cancel_count"))
    feats = feats.join(buys, on=["account_id", "trade_date", "symbol"])
    feats = feats.join(sells, on=["account_id", "trade_date", "symbol"])
    feats = feats.join(cancels, on=["account_id", "trade_date", "symbol"])
    feats[["buy_qty", "sell_qty", "cancel_count"]] = feats[
        ["buy_qty", "sell_qty", "cancel_count"]].fillna(0)
    feats["cancel_rate"] = feats["cancel_count"] / feats["order_count"]
    # Wash-trade candidate: matched buy and sell size, same account,
    # same symbol, same day, at least 500 shares each side.
    feats["wash_candidate"] = (
        (feats["buy_qty"] >= 500) & (feats["sell_qty"] >= 500)
        & (feats["buy_qty"] == feats["sell_qty"]))
    feats.to_parquet(gold_dir / "account_day_features.parquet", index=False)

    # --- CAT-ready rows (order events only; export format in cat.py) ---
    cat_events = orders[["order_id", "account_id", "symbol", "side", "qty",
                         "limit_price", "order_ts", "event",
                         "trade_date"]].copy()
    cat_events = cat_events.rename(columns={
        "order_id": "firm_order_id", "limit_price": "price",
        "order_ts": "event_ts"})
    cat_events.to_parquet(gold_dir / "cat_events.parquet", index=False)

    # --- data-quality report ---
    dq: dict = {}
    dq["silver_rows"] = {"fact_order": len(orders),
                         "fact_execution": len(executions),
                         "fact_trade": len(trades)}
    dq["completeness"] = {
        "fact_order_null_account": int(orders["account_key"].isna().sum()),
        "fact_order_null_price": int(orders["limit_price"].isna().sum()),
        "fact_execution_null_price": int(executions["price"].isna().sum()),
    }
    dq["uniqueness"] = {
        "fact_order_dup_ids": int(orders["order_id"].duplicated().sum()),
        "fact_execution_dup_ids": int(
            executions["exec_id"].duplicated().sum()),
        "fact_trade_dup_ids": int(trades["trade_id"].duplicated().sum()),
    }
    # Reconciliation: gold notional must equal silver NEW-order notional.
    silver_notional = float((new_orders["qty"]
                             * new_orders["limit_price"]).sum())
    gold_notional = float(feats["notional"].sum())
    dq["reconciliation"] = {
        "silver_new_order_notional": round(silver_notional, 2),
        "gold_features_notional": round(gold_notional, 2),
        "difference": round(abs(silver_notional - gold_notional), 2),
        "matches": abs(silver_notional - gold_notional) < 0.01,
    }
    dq["wash_candidates"] = int(feats["wash_candidate"].sum())
    dq["wash_candidate_accounts"] = sorted(
        feats.loc[feats["wash_candidate"], "account_id"].unique().tolist())
    dq["gold_rows"] = {"account_day_features": len(feats),
                       "cat_events": len(cat_events)}
    return dq
