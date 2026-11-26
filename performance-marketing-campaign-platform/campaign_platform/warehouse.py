"""Medallion warehouse: bronze / silver / gold Parquet writes + campaign dim.

Bronze keeps the raw normalised rows untouched. Silver keeps the cleaned,
deduplicated rows. Gold holds daily aggregates per platform and campaign
with derived metrics (CTR, CPC, CPA) that the planning tools and the data
science workflows read. The campaign dimension is SCD Type 2: a budget
change closes the old row and opens a new current one.

Databricks mapping: bronze/silver/gold are Delta tables (this local run
writes Parquet with the same partitioning); Snowflake mapping: the same
tables load through an external stage into Snowflake managed tables.
Spark mapping: gold is a GROUP BY over silver with SUM() and derived
columns; dedupe is ROW_NUMBER() as in ingest.
"""

from __future__ import annotations

from pathlib import Path


def build_campaign_dim(campaigns: list[dict]) -> list[dict]:
    """SCD Type 2 dimension rows: one current row per campaign."""
    dim: list[dict] = []
    for campaign in campaigns:
        dim.append({
            "campaign_id": campaign["campaign_id"],
            "platform": campaign["platform"],
            "total_budget": campaign["total_budget"],
            "target_cpa": campaign["target_cpa"],
            "effective_from": campaign["flight_start"],
            "effective_to": None,
            "is_current": True,
        })
    return dim


def apply_budget_change(dim: list[dict], campaign_id: str,
                        new_budget: float, effective_from: str) -> list[dict]:
    """Close the current dimension row and open a new one (SCD2)."""
    out: list[dict] = []
    for row in dim:
        if row["campaign_id"] == campaign_id and row["is_current"]:
            closed = dict(row)
            closed["effective_to"] = effective_from
            closed["is_current"] = False
            out.append(closed)
            new_row = dict(row)
            new_row["total_budget"] = new_budget
            new_row["effective_from"] = effective_from
            new_row["effective_to"] = None
            new_row["is_current"] = True
            out.append(new_row)
        else:
            out.append(row)
    return out


def write_medallion(raw_frame, clean_frame, out_dir: str | Path) -> dict:
    """Write bronze (raw), silver (clean) and gold (daily aggregates)."""
    import pandas as pd

    out = Path(out_dir)
    (out / "bronze").mkdir(parents=True, exist_ok=True)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "gold").mkdir(parents=True, exist_ok=True)

    bronze_path = out / "bronze" / "delivery.parquet"
    raw_frame.to_parquet(bronze_path, index=False)
    silver_path = out / "silver" / "delivery.parquet"
    clean_frame.to_parquet(silver_path, index=False)

    if clean_frame.empty:
        gold = pd.DataFrame(columns=[
            "date", "platform", "campaign_id", "impressions", "clicks",
            "spend", "conversions", "ctr", "cpc", "cpa"])
    else:
        gold = (
            clean_frame.groupby(["date", "platform", "campaign_id"], as_index=False)
            .agg(impressions=("impressions", "sum"),
                 clicks=("clicks", "sum"),
                 spend=("spend", "sum"),
                 conversions=("conversions", "sum"))
        )
        gold["ctr"] = (gold["clicks"] / gold["impressions"]).round(4)
        gold["cpc"] = (gold["spend"] / gold["clicks"]).round(4)
        gold["cpa"] = gold.apply(
            lambda r: round(r["spend"] / r["conversions"], 2)
            if r["conversions"] > 0 else None, axis=1)
    gold_path = out / "gold" / "daily_campaign.parquet"
    gold.to_parquet(gold_path, index=False)
    return {
        "bronze": str(bronze_path),
        "silver": str(silver_path),
        "gold": str(gold_path),
        "bronze_rows": len(raw_frame),
        "silver_rows": len(clean_frame),
        "gold_rows": len(gold),
    }
