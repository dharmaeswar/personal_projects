"""Spark-SQL-like transformations, written with pandas.

Each function names the Spark operation it mirrors so the mapping is
explicit; the pandas code is the local stand-in for a Spark DataFrame op.

- select / withColumn  -> column selection and derived columns
- filter (WHERE)       -> boolean masks
- dropDuplicates / window row_number() -> dedup, latest ingested_at wins
- join (broadcast)     -> merge against the small product dimension
- groupBy.agg          -> daily revenue aggregates
- partitionBy          -> Parquet partitioned writes by event_date
"""
import pandas as pd

from .data import ALLOWED_END, ALLOWED_START, PRODUCT_DIM


def with_derived_columns(df):
    """withColumn: amount_band from amount; is_high_value flag."""
    out = df.copy()
    out["amount_band"] = pd.cut(
        out["amount"],
        bins=[-float("inf"), 50, 100, float("inf")],
        labels=["low", "medium", "high"],
    ).astype(str)
    out["is_high_value"] = out["amount"] >= 100
    return out


def dedupe_latest(df):
    """Window: ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at DESC).

    Keeps the latest copy of each event_id; returns (deduped, n_duplicates).
    """
    ordered = df.sort_values("ingested_at", ascending=False)
    deduped = ordered.drop_duplicates(subset=["event_id"], keep="first")
    return deduped.reset_index(drop=True), len(df) - len(deduped)


def join_product_dim(df):
    """Broadcast join against the small product dimension (4 rows)."""
    merged = df.merge(
        PRODUCT_DIM[["product_code", "product_category"]],
        on="product_code",
        how="left",
    )
    return merged


def filter_valid(df):
    """WHERE clause: the quality rules, applied as one boolean mask.

    Returns (valid, invalid) where invalid carries a `violation` column.
    """
    df = df.copy()
    violations = pd.Series("", index=df.index, dtype=object)

    def flag(mask, rule):
        nonlocal violations
        hit = mask & (violations == "")
        violations = violations.mask(hit, rule)
        multi = mask & (violations != "") & (violations != rule)
        violations = violations.mask(multi, violations[multi] + "+" + rule)

    flag(df["user_id"].isna(), "null_user_id")
    flag(df["amount"] < 0, "negative_amount")
    flag(~df["product_code"].isin(PRODUCT_DIM["product_code"]), "unknown_product")
    flag((df["event_date"] < ALLOWED_START) | (df["event_date"] > ALLOWED_END), "date_out_of_range")
    flag((df["amount"] - df["quantity"] * df["unit_price"]).abs() > 0.01, "amount_mismatch")
    flag(df["quantity"] <= 0, "bad_quantity")

    invalid = df[violations != ""].copy()
    invalid["violation"] = violations[violations != ""]
    valid = df[violations == ""].copy()
    return valid.reset_index(drop=True), invalid.reset_index(drop=True)


def aggregate_daily(df):
    """GROUP BY event_date, region, product_category: revenue and order counts."""
    gold = (
        df.groupby(["event_date", "region", "product_category"], as_index=False)
        .agg(total_revenue=("amount", "sum"), orders=("event_id", "count"))
        .sort_values(["event_date", "region", "product_category"])
        .reset_index(drop=True)
    )
    gold["total_revenue"] = gold["total_revenue"].round(2)
    return gold


def reconcile(cleansed, gold):
    """Gold daily revenue must equal cleansed revenue grouped the same way."""
    expected = aggregate_daily(cleansed)
    merged = gold.merge(
        expected,
        on=["event_date", "region", "product_category"],
        suffixes=("_gold", "_expected"),
    )
    diff = (merged["total_revenue_gold"] - merged["total_revenue_expected"]).abs().max()
    return {
        "gold_rows": len(gold),
        "expected_rows": len(expected),
        "max_revenue_diff": round(float(diff), 4) if len(merged) else 0.0,
        "passed": len(gold) == len(expected) and float(diff) <= 0.01,
    }
