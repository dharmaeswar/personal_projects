"""Star-schema data model for interaction analytics.

fact_interactions is the grain of one event; dim_user and dim_content are
conformed dimensions, dim_date is the calendar. dim_content is SCD Type 2:
when a title's genre or title type changes, the current row is closed and a
new row opens, so historical facts keep pointing at the version that was
true when the event happened.

Spark / Databricks equivalents: Delta tables with ``MERGE`` for the SCD2
upsert, and a gold-layer star schema queried with Spark SQL.
"""

from __future__ import annotations

import pandas as pd

FAR_FUTURE = pd.Timestamp("9999-12-31")


def build_dim_user(clean: pd.DataFrame) -> pd.DataFrame:
    """One row per user: first seen, home country, most-used device."""
    first = clean.sort_values("event_ts").groupby("user_id").first().reset_index()
    device = (
        clean.groupby(["user_id", "device"]).size().reset_index(name="n")
        .sort_values(["user_id", "n"], ascending=[True, False])
        .drop_duplicates("user_id")[["user_id", "device"]]
        .rename(columns={"device": "primary_device"})
    )
    dim = first[["user_id", "event_ts", "country"]].rename(
        columns={"event_ts": "first_seen_ts"})
    return dim.merge(device, on="user_id", how="left").sort_values("user_id").reset_index(drop=True)


def build_dim_content(clean: pd.DataFrame) -> pd.DataFrame:
    """SCD2 content dimension: one current row per title to start."""
    latest = clean.sort_values("event_ts").groupby("content_id").last().reset_index()
    dim = latest[["content_id", "genre", "title_type", "content_duration_s"]].copy()
    dim["valid_from"] = pd.to_datetime(clean["event_ts"]).min()
    dim["valid_to"] = FAR_FUTURE
    dim["is_current"] = True
    return dim.sort_values("content_id").reset_index(drop=True)


def apply_content_change(dim: pd.DataFrame, content_id: str, effective_ts,
                         **changes) -> pd.DataFrame:
    """Close the current SCD2 row for a title and open a new one with the changes."""
    dim = dim.copy()
    effective_ts = pd.Timestamp(effective_ts)
    current = dim[(dim["content_id"] == content_id) & (dim["is_current"])]
    if current.empty:
        raise ValueError(f"no current row for content {content_id}")
    idx = current.index[0]
    dim.loc[idx, "valid_to"] = effective_ts
    dim.loc[idx, "is_current"] = False
    new_row = dim.loc[idx].copy()
    for key, value in changes.items():
        new_row[key] = value
    new_row["valid_from"] = effective_ts
    new_row["valid_to"] = FAR_FUTURE
    new_row["is_current"] = True
    out = pd.concat([dim, new_row.to_frame().T], ignore_index=True)
    # concat via a Series frame coerces columns to object; restore dtypes.
    out["is_current"] = out["is_current"].astype(bool)
    out["valid_from"] = pd.to_datetime(out["valid_from"])
    out["valid_to"] = pd.to_datetime(out["valid_to"])
    return out


def build_dim_date(clean: pd.DataFrame) -> pd.DataFrame:
    """Calendar dimension covering every event date."""
    dates = pd.to_datetime(clean["event_ts"]).dt.normalize().drop_duplicates().sort_values()
    dim = pd.DataFrame({"date": dates})
    dim["year"] = dim["date"].dt.year
    dim["month"] = dim["date"].dt.month
    dim["day"] = dim["date"].dt.day
    dim["day_of_week"] = dim["date"].dt.day_name()
    dim["is_weekend"] = dim["date"].dt.day_of_week >= 5
    return dim.reset_index(drop=True)


def build_fact_interactions(clean: pd.DataFrame, dim_user: pd.DataFrame,
                            dim_content: pd.DataFrame) -> pd.DataFrame:
    """Event-grain fact table with surrogate keys into the dimensions."""
    fact = clean.copy()
    fact["date_key"] = pd.to_datetime(fact["event_ts"]).dt.normalize()
    fact = fact.merge(dim_user[["user_id"]], on="user_id", how="left")
    current_content = dim_content[dim_content["is_current"]][["content_id"]]
    fact = fact.merge(current_content, on="content_id", how="left")
    return fact[[
        "event_id", "user_id", "content_id", "event_type", "event_ts",
        "date_key", "device", "surface", "country", "watch_seconds",
    ]].sort_values("event_ts").reset_index(drop=True)
