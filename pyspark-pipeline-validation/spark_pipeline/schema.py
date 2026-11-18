"""Expected schema for the raw event table, enforced before any write.

Mirrors a Spark StructType: column, pandas dtype, nullable flag.
"""
import pandas as pd

EXPECTED_SCHEMA = {
    "event_id": ("object", False),
    "user_id": ("object", False),
    "product_code": ("object", False),
    "region": ("object", False),
    "channel": ("object", False),
    "event_date": ("object", False),
    "quantity": ("int64", False),
    "unit_price": ("float64", False),
    "amount": ("float64", False),
    "ingested_at": ("object", False),
}


def check_schema(df, allow_nulls=False):
    """Return a list of schema violations; empty list means the schema holds.

    Raw input is checked with allow_nulls=True: nulls and bad values are
    exactly what the quality checks are meant to catch and quarantine.
    Cleansed output is checked strictly (allow_nulls=False).
    """
    problems = []
    for col, (dtype, nullable) in EXPECTED_SCHEMA.items():
        if col not in df.columns:
            problems.append(f"missing column: {col}")
            continue
        if str(df[col].dtype) != dtype:
            problems.append(f"{col}: dtype {df[col].dtype}, expected {dtype}")
        if not nullable and not allow_nulls and df[col].isna().any():
            problems.append(f"{col}: {int(df[col].isna().sum())} null values")
    extra = sorted(set(df.columns) - set(EXPECTED_SCHEMA))
    if extra:
        problems.append(f"unexpected columns: {extra}")
    return problems


def enforce_schema(df, allow_nulls=False):
    problems = check_schema(df, allow_nulls=allow_nulls)
    if problems:
        raise ValueError("Schema enforcement failed: " + "; ".join(problems))
    return df
