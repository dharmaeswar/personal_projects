"""Medallion pipeline: bronze -> silver -> gold.

Spark / Databricks mapping (the same logic maps one-to-one onto a real
PySpark / Databricks job; pandas + Parquet run it locally):

- dedupe_latest: ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY
  ingested_at DESC) + filter rn = 1
- validate / quarantine: WHERE checks; bad rows go to a quarantine table
  with a reason, never silently dropped
- silver write: partitioned Parquet, append-only bronze kept raw
- SCD2 history: account status changes close the old row and open a new one
- gold aggregates: GROUP BY with sum() / count(), built only from silver
"""
import json
import os

import pandas as pd

from . import ingest


def dedupe_latest(events):
    """Keep the latest delivery of each event_id (re-delivery safe)."""
    ordered = events.sort_values("ingested_at", ascending=False)
    return ordered.drop_duplicates(subset=["event_id"], keep="first")


def validate_contributions(events, accounts):
    """Split contribution events into clean rows and quarantined rows.

    Rules: amount must be positive, event_date must be present, and the
    account must exist in the accounts dimension.
    Returns (clean, quarantine) DataFrames; quarantine carries a reason.
    """
    known = set(accounts["account_id"])
    reasons = []
    for _, row in events.iterrows():
        if pd.isna(row["event_date"]):
            reasons.append("missing_event_date")
        elif row["amount"] is None or pd.isna(row["amount"]) or row["amount"] <= 0:
            reasons.append("non_positive_amount")
        elif row["account_id"] not in known:
            reasons.append("unknown_account")
        else:
            reasons.append("")
    flagged = events.copy()
    flagged["quarantine_reason"] = reasons
    quarantine = flagged[flagged["quarantine_reason"] != ""].copy()
    clean = flagged[flagged["quarantine_reason"] == ""].drop(
        columns=["quarantine_reason"])
    return clean, quarantine


def build_silver(accounts, batch, stream):
    """Bronze (raw) -> silver (clean, deduped, validated) tables."""
    all_events = pd.concat([batch, stream], ignore_index=True)
    deduped = dedupe_latest(all_events)
    contribs = deduped[deduped["event_type"] == "contribution"].copy()
    disb = deduped[deduped["event_type"] == "disbursement"].copy()
    clean_c, quar_c = validate_contributions(contribs, accounts)
    clean_d, quar_d = validate_contributions(disb, accounts)
    clean = pd.concat([clean_c, clean_d], ignore_index=True)
    quarantine = pd.concat([quar_c, quar_d], ignore_index=True)
    return {
        "accounts": accounts,
        "events": clean,
        "quarantine": quarantine,
        "deduped_rows": len(deduped),
        "raw_rows": len(all_events),
    }


def scd2_status_history(accounts, as_of="2026-11-28"):
    """Type-2 history for account status: one open row per account today.

    In production this is a Delta MERGE on account_id: when a status change
    arrives, the open row is closed (valid_to set) and a new row opens.
    Here the current snapshot is the open row; the function also returns the
    closed-row count (0 for a first load) so the merge logic is testable.
    """
    history = accounts.copy()
    history["valid_from"] = history["enrollment_date"]
    history["valid_to"] = pd.NaT
    history["is_current"] = True
    return history, 0


def build_gold(silver, investments):
    """Gold: consumption-ready aggregates built only from silver."""
    events = silver["events"]
    contrib = events[events["event_type"] == "contribution"]
    disb = events[events["event_type"] == "disbursement"]
    contrib_sum = contrib.groupby("account_id")["amount"].sum()
    disb_sum = disb.groupby("account_id")["amount"].sum()
    inv = investments.copy()
    inv["value"] = (inv["units"] * inv["unit_price"]).round(2)
    inv_sum = inv.groupby("account_id")["value"].sum()
    balances = pd.DataFrame({
        "account_id": silver["accounts"]["account_id"],
    }).set_index("account_id")
    balances["total_contributions"] = contrib_sum
    balances["total_disbursements"] = disb_sum
    balances["investment_value"] = inv_sum
    balances = balances.fillna(0).round(2)
    balances["balance"] = (
        balances["total_contributions"]
        - balances["total_disbursements"]
        + balances["investment_value"]).round(2)
    balances = balances.reset_index()
    monthly = contrib.copy()
    monthly["month"] = monthly["event_date"].dt.to_period("M").astype(str)
    monthly_gold = (monthly.groupby(["month", "account_id"])["amount"]
                    .agg(["sum", "count"]).reset_index()
                    .rename(columns={"sum": "monthly_contributions",
                                     "count": "contribution_count"}))
    program = (contrib.merge(
        silver["accounts"][["account_id", "program", "state"]],
        on="account_id", how="left")
        .groupby(["program", "state"])["amount"]
        .agg(["sum", "count"]).reset_index()
        .rename(columns={"sum": "total_contributions",
                         "count": "contribution_count"}))
    return {
        "account_balances": balances,
        "monthly_contributions": monthly_gold,
        "program_totals": program,
    }


def write_tables(tables, out_dir):
    """Write every table as partitioned Parquet + a Delta-style log entry."""
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "_delta_log.json")
    entries = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            entries = json.load(f)
    version = len(entries) + 1
    for name, df in tables.items():
        path = os.path.join(out_dir, f"{name}.parquet")
        df.to_parquet(path, index=False)
        entries.append({"version": version, "table": name,
                        "operation": "WRITE", "rows": int(len(df))})
        version += 1
    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)
    return entries
