"""Bronze layer: schema-enforced raw ingest into partitioned Parquet.

Each feed lands as an append-only Parquet dataset partitioned by
``trade_date`` (hive style: ``trade_date=YYYY-MM-DD``). Rows that fail
schema enforcement are quarantined with a reason instead of being
silently dropped. This mirrors the bronze layer of a Databricks / Delta
Lake pipeline; the code runs locally with pandas + pyarrow, no Spark
cluster is involved.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .generate import EXEC_COLUMNS, ORDER_COLUMNS, TRADE_COLUMNS

SCHEMAS = {
    "orders": ORDER_COLUMNS,
    "executions": EXEC_COLUMNS,
    "trades": TRADE_COLUMNS,
}

# Column -> expected kind, checked semantically (pandas 3 uses the new
# ``str`` dtype and ``datetime64[us]``, so exact dtype strings are not
# compared). Kinds: "string", "int", "float", "datetime", "date".
DTYPES = {
    "orders": {"order_id": "string", "account_id": "string",
               "symbol": "string", "side": "string", "qty": "int",
               "limit_price": "float", "order_ts": "datetime",
               "event": "string", "trade_date": "date",
               "ingested_at": "datetime"},
    "executions": {"exec_id": "string", "order_id": "string",
                   "symbol": "string", "qty": "int",
                   "price": "float", "exec_ts": "datetime",
                   "trade_date": "date", "ingested_at": "datetime"},
    "trades": {"trade_id": "string", "symbol": "string",
               "price": "float", "qty": "int",
               "trade_ts": "datetime", "trade_date": "date",
               "ingested_at": "datetime"},
}


def _kind_ok(kind: str, series: pd.Series) -> bool:
    import pandas.api.types as t
    if kind == "string":
        return bool(t.is_string_dtype(series.dtype))
    if kind == "int":
        return bool(t.is_integer_dtype(series.dtype))
    if kind == "float":
        return bool(t.is_float_dtype(series.dtype))
    if kind == "datetime":
        return bool(t.is_datetime64_any_dtype(series.dtype))
    if kind == "date":
        import datetime
        vals = series.dropna()
        return bool(t.is_object_dtype(series.dtype)) and all(
            isinstance(v, datetime.date) for v in vals)
    return False


def check_schema(name: str, df: pd.DataFrame) -> list[str]:
    """Return a list of schema violations (empty when the frame is clean)."""
    problems = []
    expected = SCHEMAS[name]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        problems.append(f"missing columns: {missing}")
    extra = [c for c in df.columns if c not in expected]
    if extra:
        problems.append(f"unexpected columns: {extra}")
    for col, kind in DTYPES[name].items():
        if col in df.columns and not _kind_ok(kind, df[col]):
            problems.append(f"{col}: dtype {df[col].dtype}, expected {kind}")
    return problems


def _quarantine_reasons(name: str, df: pd.DataFrame) -> pd.Series:
    """Per-row quarantine reason ('' means the row is clean)."""
    reason = pd.Series("", index=df.index, dtype=object)
    if name == "orders":
        reason = reason.mask(df["account_id"].isna(), "missing_account")
        reason = reason.mask(df["qty"] <= 0, "bad_qty")
        ts_date = pd.to_datetime(df["order_ts"]).dt.date
        reason = reason.mask(ts_date != df["trade_date"], "date_mismatch")
    if name == "executions":
        reason = reason.mask(df["qty"] <= 0, "bad_qty")
        ts_date = pd.to_datetime(df["exec_ts"]).dt.date
        reason = reason.mask(ts_date != df["trade_date"], "date_mismatch")
    if name == "trades":
        reason = reason.mask(df["qty"] <= 0, "bad_qty")
        ts_date = pd.to_datetime(df["trade_ts"]).dt.date
        reason = reason.mask(ts_date != df["trade_date"], "date_mismatch")
    return reason


def ingest(name: str, df: pd.DataFrame, bronze_dir: Path) -> dict:
    """Write one feed to bronze Parquet, partitioned by trade_date.

    Returns counts: rows in, rows written, rows quarantined, and the
    quarantine reasons. Raises ValueError on a schema violation.
    """
    problems = check_schema(name, df)
    if problems:
        raise ValueError(f"{name} schema violations: {problems}")
    table_dir = bronze_dir / name
    quarantine_dir = bronze_dir / f"{name}_quarantine"
    reasons = _quarantine_reasons(name, df)
    clean = df[reasons == ""].copy()
    bad = df[reasons != ""].copy()
    bad["quarantine_reason"] = reasons[reasons != ""]
    clean["trade_date"] = clean["trade_date"].astype(str)
    if len(clean):
        table = pa.Table.from_pandas(clean, preserve_index=False)
        hive = ds.partitioning(
            pa.schema([("trade_date", pa.string())]), flavor="hive")
        ds.write_dataset(table, str(table_dir), format="parquet",
                         partitioning=hive,
                         existing_data_behavior="overwrite_or_ignore")
    if len(bad):
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        bad["trade_date"] = bad["trade_date"].astype(str)
        bad_table = pa.Table.from_pandas(bad, preserve_index=False)
        pq.write_table(bad_table, str(quarantine_dir / "quarantine.parquet"))
    return {
        "feed": name,
        "rows_in": len(df),
        "rows_written": len(clean),
        "rows_quarantined": len(bad),
        "quarantine_reasons": bad["quarantine_reason"].value_counts().to_dict()
        if len(bad) else {},
        "partitions": sorted(p.name for p in table_dir.iterdir()
                            if p.is_dir()) if table_dir.exists() else [],
    }


def read_bronze(name: str, bronze_dir: Path) -> pd.DataFrame:
    """Read a bronze feed back as one DataFrame (all partitions)."""
    dataset = ds.dataset(str(bronze_dir / name), format="parquet",
                         partitioning="hive")
    return dataset.to_table().to_pandas()
