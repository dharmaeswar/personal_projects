"""Spark-SQL-like transformations for the risk-exposure ETL.

Each function names the Spark operation it mirrors so the mapping is
explicit; the pandas code is the local stand-in for a Spark DataFrame op.

- select / withColumn  -> column selection and derived columns
- filter (WHERE)       -> boolean masks
- dropDuplicates / window row_number() -> dedup, latest ingested_at wins
- join (broadcast)     -> merge against the small book dimension
- groupBy.agg          -> daily exposure aggregates
- partitionBy          -> Parquet partitioned writes by trade_date
"""
import pandas as pd

from .risk_data import ALLOWED_END, ALLOWED_START, BOOK_DIM, INSTRUMENT_FACTOR


def with_derived_risk_columns(df):
    """withColumn: exposure_band from exposure; is_high_exposure flag."""
    out = df.copy()
    out["exposure_band"] = pd.cut(
        out["exposure"],
        bins=[-float("inf"), 100_000, 500_000, float("inf")],
        labels=["low", "medium", "high"],
    ).astype(str)
    out["is_high_exposure"] = out["exposure"] >= 500_000
    return out


def dedupe_latest_risk(df):
    """Window: ROW_NUMBER() OVER (PARTITION BY trade_id ORDER BY ingested_at DESC).

    Keeps the latest copy of each trade_id; returns (deduped, n_duplicates).
    """
    ordered = df.sort_values("ingested_at", ascending=False)
    deduped = ordered.drop_duplicates(subset=["trade_id"], keep="first")
    return deduped.reset_index(drop=True), len(df) - len(deduped)


def join_book_dim(df):
    """Broadcast join against the small book dimension (4 rows)."""
    merged = df.merge(
        BOOK_DIM[["book", "desk"]],
        on="book",
        how="left",
    )
    return merged


def filter_valid_risk(df):
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

    flag(df["counterparty"].isna(), "null_counterparty")
    flag(df["notional"] < 0, "negative_notional")
    flag(~df["book"].isin(BOOK_DIM["book"]), "unknown_book")
    flag((df["trade_date"] < ALLOWED_START) | (df["trade_date"] > ALLOWED_END), "date_out_of_range")
    expected = df["notional"] * df["instrument_type"].map(INSTRUMENT_FACTOR)
    flag((df["exposure"] - expected).abs() > 0.01, "exposure_mismatch")

    invalid = df[violations != ""].copy()
    invalid["violation"] = violations[violations != ""]
    valid = df[violations == ""].copy()
    return valid.reset_index(drop=True), invalid.reset_index(drop=True)


def aggregate_risk_daily(df):
    """GROUP BY trade_date, book: total notional, total exposure, trade counts."""
    gold = (
        df.groupby(["trade_date", "book"], as_index=False)
        .agg(
            total_notional=("notional", "sum"),
            total_exposure=("exposure", "sum"),
            trades=("trade_id", "count"),
        )
        .sort_values(["trade_date", "book"])
        .reset_index(drop=True)
    )
    gold["total_notional"] = gold["total_notional"].round(2)
    gold["total_exposure"] = gold["total_exposure"].round(2)
    return gold


def reconcile_risk(cleansed, gold):
    """Gold daily exposure must equal cleansed exposure grouped the same way."""
    expected = aggregate_risk_daily(cleansed)
    merged = gold.merge(
        expected,
        on=["trade_date", "book"],
        suffixes=("_gold", "_expected"),
    )
    diff = (merged["total_exposure_gold"] - merged["total_exposure_expected"]).abs().max()
    return {
        "gold_rows": len(gold),
        "expected_rows": len(expected),
        "max_exposure_diff": round(float(diff), 4) if len(merged) else 0.0,
        "passed": len(gold) == len(expected) and float(diff) <= 0.01,
    }
