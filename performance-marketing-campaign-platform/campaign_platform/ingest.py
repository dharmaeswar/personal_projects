"""Platform delivery ingest: schema contracts + normalisation.

Each ad platform reports the same delivery facts under different field
names. Ingest validates every row against the platform's contract,
quarantines contract breaks with a reason, and normalises the survivors
to one common schema.

Spark mapping (what each step becomes in a real PySpark job):
  validate_contract -> DataFrame.filter() with the contract predicates
  normalize         -> withColumn() renames + cast() to the common schema
  dedupe            -> ROW_NUMBER() OVER (PARTITION BY platform, campaign_id,
                       date ORDER BY ingested_at DESC) + filter rn = 1
"""

from __future__ import annotations

import random

PLATFORMS = ("google_ads", "meta", "dv360", "trade_desk", "yahoo")

# Native field name per platform for the same concept.
NATIVE_FIELDS = {
    "google_ads": {"spend": "cost", "conversions": "conversions"},
    "meta": {"spend": "spend", "conversions": "actions"},
    "dv360": {"spend": "media_cost", "conversions": "conversions"},
    "trade_desk": {"spend": "spend", "conversions": "conversions"},
    "yahoo": {"spend": "cost", "conversions": "conversions"},
}

COMMON_COLUMNS = [
    "date", "platform", "campaign_id",
    "impressions", "clicks", "spend", "conversions",
]

REQUIRED_COMMON = ("campaign_id", "date", "impressions", "clicks")


def native_columns(platform: str) -> list[str]:
    """Column names a raw row from this platform must carry."""
    fields = NATIVE_FIELDS[platform]
    return ["campaign_id", "date", "impressions", "clicks",
            fields["spend"], fields["conversions"]]


def generate_platform_rows(platform: str, campaign_ids: list[str],
                           n_days: int = 14, seed: int = 42,
                           daily_budget: float | None = None) -> list[dict]:
    """Seeded synthetic daily delivery rows for one platform.

    All data is synthetic (seed 42). No real campaign, advertiser or
    performance data is used. When daily_budget is given, volumes are
    scaled so expected daily spend lands near that budget (with natural
    day-to-day variance); otherwise raw volumes are used as-is.
    """
    rng = random.Random(hash((platform, seed)) % (2 ** 31))
    spend_field = NATIVE_FIELDS[platform]["spend"]
    conv_field = NATIVE_FIELDS[platform]["conversions"]
    rows: list[dict] = []
    for day in range(n_days):
        date = f"2026-10-{day + 1:02d}"
        for campaign_id in campaign_ids:
            if daily_budget is not None:
                target_spend = daily_budget * rng.uniform(0.7, 1.1)
                cpc = rng.uniform(0.60, 2.40)
                clicks = max(1, int(target_spend / cpc))
                ctr = rng.uniform(0.008, 0.045)
                impressions = int(clicks / ctr)
                spend = round(clicks * cpc, 2)
            else:
                impressions = rng.randint(8_000, 120_000)
                clicks = int(impressions * rng.uniform(0.008, 0.045))
                spend = round(clicks * rng.uniform(0.60, 2.40), 2)
            conversions = int(clicks * rng.uniform(0.02, 0.12))
            row = {
                "campaign_id": campaign_id,
                "date": date,
                "impressions": impressions,
                "clicks": clicks,
                spend_field: spend,
                conv_field: conversions,
            }
            rows.append(row)
    return rows


def validate_contract(rows: list[dict], platform: str) -> tuple[list[dict], list[dict]]:
    """Split rows into valid rows and quarantined rows (with a reason).

    A row fails when a required native column is missing, a value has the
    wrong type, or a range rule breaks (negative spend, clicks above
    impressions, negative conversions).
    """
    required = native_columns(platform)
    spend_field = NATIVE_FIELDS[platform]["spend"]
    conv_field = NATIVE_FIELDS[platform]["conversions"]
    valid, quarantined = [], []
    for row in rows:
        reason = None
        for col in required:
            if col not in row or row[col] is None:
                reason = f"missing required column: {col}"
                break
        if reason is None:
            if not isinstance(row["impressions"], int) or row["impressions"] < 0:
                reason = "impressions must be a non-negative integer"
            elif not isinstance(row["clicks"], int) or row["clicks"] < 0:
                reason = "clicks must be a non-negative integer"
            elif row["clicks"] > row["impressions"]:
                reason = "clicks exceed impressions"
            elif row[spend_field] < 0:
                reason = "spend must be non-negative"
            elif row[conv_field] < 0:
                reason = "conversions must be non-negative"
        if reason is None:
            valid.append(row)
        else:
            bad = dict(row)
            bad["_quarantine_reason"] = reason
            quarantined.append(bad)
    return valid, quarantined


def normalize(rows: list[dict], platform: str):
    """Map one platform's native rows onto the common schema (pandas)."""
    import pandas as pd

    spend_field = NATIVE_FIELDS[platform]["spend"]
    conv_field = NATIVE_FIELDS[platform]["conversions"]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=COMMON_COLUMNS)
    frame = frame.rename(columns={spend_field: "spend", conv_field: "conversions"})
    frame["platform"] = platform
    frame = frame[COMMON_COLUMNS]
    for col in ("impressions", "clicks"):
        frame[col] = frame[col].astype("int64")
    for col in ("spend", "conversions"):
        frame[col] = frame[col].astype("float64")
    return frame


def dedupe(frame):
    """Keep the latest row per (platform, campaign_id, date)."""
    if frame.empty:
        return frame
    return frame.drop_duplicates(
        subset=["platform", "campaign_id", "date"], keep="last"
    ).reset_index(drop=True)
