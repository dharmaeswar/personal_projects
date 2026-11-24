"""Data-quality checks with quarantine and retry.

Bad rows are never dropped silently: each failed check names the rule that
fired, and the row lands in a quarantine table with its reason. A retry
queue holds quarantined rows that a fixed source could re-deliver; this
module can re-check a corrected row and promote it back into silver.
"""

from __future__ import annotations

import pandas as pd

MAX_SEND_DATE = "2026-12-31"
KNOWN_CAMPAIGNS = {"CMP-101", "CMP-102", "CMP-103", "CMP-104", "CMP-105"}


def _quarantine_row(row, reason):
    out = dict(row)
    out["quarantine_reason"] = reason
    return out


def check_messages(df):
    """Validate raw message rows. Returns (clean_df, quarantine_df)."""
    clean, quarantined = [], []
    seen_ids = set()
    for _, row in df.iterrows():
        r = row.to_dict()
        if r["message_id"] in seen_ids:
            quarantined.append(_quarantine_row(r, "duplicate message_id"))
            continue
        seen_ids.add(r["message_id"])
        if pd.isna(r["campaign_id"]):
            quarantined.append(_quarantine_row(r, "null campaign_id"))
            continue
        if str(r["send_date"]) > MAX_SEND_DATE:
            quarantined.append(_quarantine_row(r, "send_date after 2026-12-31"))
            continue
        if int(r["audience_size"]) <= 0:
            quarantined.append(_quarantine_row(r, "audience_size <= 0"))
            continue
        clean.append(r)
    clean_df = pd.DataFrame(clean, columns=list(df.columns)) if clean else pd.DataFrame(columns=list(df.columns))
    q_df = (
        pd.DataFrame(quarantined)
        if quarantined
        else pd.DataFrame(columns=list(df.columns) + ["quarantine_reason"])
    )
    return clean_df, q_df


def check_metrics(df):
    """Validate raw vendor metric rows. Returns (clean_df, quarantine_df)."""
    clean, quarantined = [], []
    for _, row in df.iterrows():
        r = row.to_dict()
        if r["campaign_id"] not in KNOWN_CAMPAIGNS:
            quarantined.append(_quarantine_row(r, "unknown campaign_id"))
            continue
        if int(r["opens"]) < 0 or int(r["clicks"]) < 0 or int(r["unsubscribes"]) < 0:
            quarantined.append(_quarantine_row(r, "negative metric value"))
            continue
        if str(r["event_date"]) > MAX_SEND_DATE:
            quarantined.append(_quarantine_row(r, "event_date after 2026-12-31"))
            continue
        clean.append(r)
    clean_df = pd.DataFrame(clean, columns=list(df.columns)) if clean else pd.DataFrame(columns=list(df.columns))
    q_df = (
        pd.DataFrame(quarantined)
        if quarantined
        else pd.DataFrame(columns=list(df.columns) + ["quarantine_reason"])
    )
    return clean_df, q_df


def retry_quarantined(quarantine_df, fixed_rows):
    """Re-check corrected rows; returns (promoted_df, still_quarantined_df).

    `fixed_rows` is a list of dicts with the same columns as the quarantine
    table minus `quarantine_reason`. Each fixed row is re-validated with the
    message rules; rows that pass are promoted, the rest stay quarantined.
    """
    promoted, still = [], []
    fixed_by_id = {r.get("message_id", r.get("campaign_id")): r for r in fixed_rows}
    for _, row in quarantine_df.iterrows():
        r = row.to_dict()
        key = r.get("message_id", r.get("campaign_id"))
        fixed = fixed_by_id.get(key)
        if fixed is None:
            still.append(r)
            continue
        candidate = pd.DataFrame([fixed])
        clean, _ = check_messages(candidate)
        if len(clean) == 1:
            promoted.append(fixed)
        else:
            still.append(r)
    cols = list(quarantine_df.columns)
    promoted_df = pd.DataFrame(promoted) if promoted else pd.DataFrame(columns=[c for c in cols if c != "quarantine_reason"])
    still_df = pd.DataFrame(still) if still else pd.DataFrame(columns=cols)
    return promoted_df, still_df


def reconcile_gold_to_silver(gold_df, silver_messages_df, silver_metrics_df):
    """Gold daily engagement must reconcile to silver inputs.

    Returns a list of mismatch descriptions (empty when reconciled).
    """
    problems = []
    expected_opens = int(silver_metrics_df["opens"].sum())
    expected_clicks = int(silver_metrics_df["clicks"].sum())
    if int(gold_df["total_opens"].sum()) != expected_opens:
        problems.append(
            f"total_opens mismatch: gold {int(gold_df['total_opens'].sum())} vs silver {expected_opens}"
        )
    if int(gold_df["total_clicks"].sum()) != expected_clicks:
        problems.append(
            f"total_clicks mismatch: gold {int(gold_df['total_clicks'].sum())} vs silver {expected_clicks}"
        )
    expected_msgs = len(silver_messages_df)
    if int(gold_df["messages_sent"].sum()) != expected_msgs:
        problems.append(
            f"messages_sent mismatch: gold {int(gold_df['messages_sent'].sum())} vs silver {expected_msgs}"
        )
    return problems
