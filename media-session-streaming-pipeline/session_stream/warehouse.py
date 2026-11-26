"""Bronze / silver / gold lakehouse writes and the star-schema model.

Local mirror of a Delta Lake medallion layout on Databricks: bronze keeps
raw events as landed, silver holds cleansed events, gold holds the
session fact and window aggregates. Parquet files are partitioned the way
Delta tables are (by event_date, then title or region), so the layout maps
directly onto ``df.write.partitionBy(...).format("delta")``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _add_event_date(df: pd.DataFrame, ts_col: str = "event_ts") -> pd.DataFrame:
    d = df.copy()
    d["event_ts"] = pd.to_datetime(d["event_ts"], utc=True)
    d["event_date"] = d["event_ts"].dt.strftime("%Y-%m-%d")
    return d


def write_bronze(df: pd.DataFrame, base: Path) -> list[Path]:
    """Write raw events partitioned by event_date (Delta bronze)."""
    d = _add_event_date(df)
    out: list[Path] = []
    for date, part in d.groupby("event_date"):
        p = Path(base) / "bronze" / f"event_date={date}" / "part-00000.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["event_date"]).to_parquet(p, index=False)
        out.append(p)
    return out


def write_silver(df: pd.DataFrame, base: Path) -> list[Path]:
    """Write cleansed events partitioned by event_date and title_id."""
    d = _add_event_date(df)
    out: list[Path] = []
    for (date, title), part in d.groupby(["event_date", "title_id"]):
        p = (Path(base) / "silver" / f"event_date={date}"
             / f"title_id={title}" / "part-00000.parquet")
        p.parent.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["event_date"]).to_parquet(p, index=False)
        out.append(p)
    return out


def write_gold_sessions(sessions: pd.DataFrame, base: Path) -> list[Path]:
    """Write the session fact table, partitioned by session date."""
    if sessions.empty:
        return []
    d = sessions.copy()
    d["session_start"] = pd.to_datetime(d["session_start"], utc=True)
    d["event_date"] = d["session_start"].dt.strftime("%Y-%m-%d")
    out: list[Path] = []
    for date, part in d.groupby("event_date"):
        p = (Path(base) / "gold" / "fact_session"
             / f"event_date={date}" / "part-00000.parquet")
        p.parent.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["event_date"]).to_parquet(p, index=False)
        out.append(p)
    return out


def build_title_dimension(titles: list[dict]) -> pd.DataFrame:
    """Build the title dimension with SCD2 columns.

    Each title row carries valid_from / valid_to / is_current, so a title
    rename or genre change closes the old row and opens a new one instead
    of overwriting history.
    """
    rows = []
    for t in titles:
        rows.append({
            "title_key": t["title_id"],
            "title_id": t["title_id"],
            "title_name": t.get("title_name", t["title_id"]),
            "genre": t.get("genre", "unknown"),
            "valid_from": pd.Timestamp("2026-01-01", tz="UTC"),
            "valid_to": pd.NaT,
            "is_current": True,
        })
    dim = pd.DataFrame(rows)
    # Keep both validity columns tz-aware UTC so SCD2 updates can assign
    # tz-aware effective timestamps without a dtype error.
    dim["valid_from"] = pd.to_datetime(dim["valid_from"], utc=True)
    dim["valid_to"] = pd.to_datetime(dim["valid_to"], utc=True)
    return dim


def update_title_dimension(dim: pd.DataFrame, title_id: str,
                           new_name: str,
                           effective: datetime | None = None
                           ) -> pd.DataFrame:
    """SCD2 update: close the current row, open a new one with the new name."""
    eff = effective or datetime(2026, 11, 26, tzinfo=timezone.utc)
    d = dim.copy()
    cur = d["is_current"] & (d["title_id"] == title_id)
    if not cur.any():
        raise ValueError(f"no current row for title {title_id}")
    old = d[cur].iloc[0].copy()
    d.loc[cur, "valid_to"] = pd.Timestamp(eff)
    d.loc[cur, "is_current"] = False
    new = old.copy()
    new["title_name"] = new_name
    new["valid_from"] = pd.Timestamp(eff)
    new["valid_to"] = pd.NaT
    new["is_current"] = True
    return pd.concat([d, pd.DataFrame([new])], ignore_index=True)


def build_session_fact(sessions: pd.DataFrame,
                       dim: pd.DataFrame) -> pd.DataFrame:
    """Join sessions to the current title dimension (star schema fact)."""
    cur = dim[dim["is_current"]][["title_id", "title_key", "title_name", "genre"]]
    fact = sessions.merge(cur, on="title_id", how="left")
    fact["date_key"] = pd.to_datetime(
        fact["session_start"], utc=True).dt.strftime("%Y%m%d")
    return fact
