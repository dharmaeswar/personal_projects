"""Bronze -> Silver -> Gold transforms for the claims lakehouse.

Spark mapping (each pandas step names its Databricks/Spark equivalent):
  dedupe_latest      ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY ingested_at DESC)
  join_member_dim    broadcast join against the 120-row member dimension
  filter_valid       WHERE with the same rules + quarantine table with a reason column
  with_derived       withColumn("paid_band", ...) / withColumn("paid_per_day", ...)
  aggregate_daily    GROUP BY service_date, plan with sum(paid_amount), count(*)
  aggregate_monthly  GROUP BY month, plan, diag_group
  partitioned write  df.write.partitionBy("service_date").parquet(...) (ADLS Gen2 layout)
  reconciliation     gold daily paid must equal silver paid grouped the same way
"""
import pandas as pd

VALID_DIAG_CODES = {"I25", "M17", "C50", "Z00", "F32"}
DATE_MIN = pd.Timestamp("2026-09-01")
DATE_MAX = pd.Timestamp("2026-11-15")


def dedupe_latest(df):
    """Window-function dedup: keep the latest copy of each claim_id."""
    return (df.sort_values("ingested_at")
              .drop_duplicates(subset="claim_id", keep="last")
              .reset_index(drop=True))


def join_member_dim(claims, members):
    """Broadcast-style join: member dimension is 120 rows, joined as a lookup."""
    return claims.merge(members, on="member_id", how="left", validate="many_to_one")


def check_row(row):
    if pd.isna(row["member_id"]):
        return "null_member_id"
    if pd.isna(row["plan"]):
        return "unknown_member"
    if row["paid_amount"] < 0:
        return "negative_paid_amount"
    if row["diag_code"] not in VALID_DIAG_CODES:
        return "unknown_diag_code"
    if not (DATE_MIN <= row["service_date"] <= DATE_MAX):
        return "service_date_out_of_range"
    if abs(row["paid_amount"] - (row["billed_amount"] - row["adjustment"])) > 0.01:
        return "paid_amount_mismatch"
    return None


def filter_valid(df):
    """Split into cleansed rows and a quarantine table with a reason per row."""
    reasons = df.apply(check_row, axis=1)
    quarantined = df[reasons.notna()].copy()
    quarantined["quarantine_reason"] = reasons[reasons.notna()]
    cleansed = df[reasons.isna()].copy().reset_index(drop=True)
    return cleansed, quarantined.reset_index(drop=True)


def with_derived(df):
    out = df.copy()
    out["paid_band"] = pd.cut(
        out["paid_amount"], bins=[-1, 500, 2000, 5000, float("inf")],
        labels=["low", "medium", "high", "very_high"])
    out["paid_band"] = out["paid_band"].astype(str)
    return out


def aggregate_daily(df):
    """Gold: daily paid totals by service date and plan."""
    return (df.groupby(["service_date", "plan"], as_index=False)
              .agg(total_paid=("paid_amount", "sum"),
                   claim_count=("claim_id", "count"),
                   avg_paid=("paid_amount", "mean"))
              .sort_values(["service_date", "plan"])
              .reset_index(drop=True))


def aggregate_monthly(df):
    """Gold: monthly paid totals by plan and diagnosis group."""
    out = df.copy()
    out["service_month"] = out["service_date"].dt.to_period("M").astype(str)
    return (out.groupby(["service_month", "plan", "diag_group"], as_index=False)
              .agg(total_paid=("paid_amount", "sum"),
                   claim_count=("claim_id", "count"))
              .sort_values(["service_month", "plan", "diag_group"])
              .reset_index(drop=True))


def reconcile(cleansed, gold_daily):
    """Gold daily totals must equal cleansed totals grouped the same way."""
    expected = (cleansed.groupby(["service_date", "plan"], as_index=False)
                .agg(total_paid=("paid_amount", "sum")))
    merged = gold_daily.merge(expected, on=["service_date", "plan"],
                              suffixes=("_gold", "_silver"))
    diff = (merged["total_paid_gold"] - merged["total_paid_silver"]).abs().max()
    return bool(diff < 0.01), float(diff)
