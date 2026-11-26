"""Spark Structured Streaming-style micro-batch processing.

Runs locally on pandas. Every operation names the Spark operation it
mirrors, so the same logic maps one-to-one onto a real Structured
Streaming job on Databricks; no cluster run is claimed here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

SESSION_GAP_MINUTES = 30
WATERMARK_LATENESS_MINUTES = 10


def to_frame(events: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(events)
    if df.empty:
        return df
    df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
    return df


def apply_watermark(df: pd.DataFrame,
                    allowed_lateness_minutes: int = WATERMARK_LATENESS_MINUTES,
                    max_seen_ts: datetime | None = None
                    ) -> tuple[pd.DataFrame, pd.DataFrame, datetime | None]:
    """Split on-time vs late events, the way a streaming watermark does.

    Mirrors ``withWatermark("event_ts", "<lateness>")``: the watermark is
    max event time seen minus allowed lateness; events older than it are
    late and must be quarantined, never silently dropped.
    Returns (on_time, late, new_max_seen_ts).
    """
    if df.empty:
        return df, df, max_seen_ts
    seen = df["event_ts"].max()
    if max_seen_ts is None or seen > max_seen_ts:
        max_seen_ts = seen.to_pydatetime()
    watermark = max_seen_ts - timedelta(minutes=allowed_lateness_minutes)
    on_time = df[df["event_ts"] >= watermark].copy()
    late = df[df["event_ts"] < watermark].copy()
    return on_time, late, max_seen_ts


def process_micro_batches(df: pd.DataFrame, trigger_minutes: int = 5,
                          allowed_lateness_minutes: int = WATERMARK_LATENESS_MINUTES
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process events in chronological micro-batches, carrying the watermark.

    This is how a Structured Streaming job actually runs: each trigger
    processes the events that arrived in a short window (here 5 minutes
    of event time), and the watermark only advances as new event time is
    seen — so in-order events are never late, and only out-of-order
    arrivals land late. Rows are processed in ARRIVAL order (the order
    given), not re-sorted by event time: that is what makes a late event
    late — it arrives after the watermark has passed its event time.
    Returns (on_time, late) across all batches.
    """
    if df.empty:
        return df, df
    d = df.reset_index(drop=True)
    on_time_parts: list[pd.DataFrame] = []
    late_parts: list[pd.DataFrame] = []
    max_seen: datetime | None = None
    batch_start: datetime | None = None
    batch_rows: list = []
    batches: list[pd.DataFrame] = []
    for _, row in d.iterrows():
        ts = row["event_ts"].to_pydatetime()
        if batch_start is None:
            batch_start = ts
        if ts > batch_start + timedelta(minutes=trigger_minutes):
            batches.append(pd.DataFrame(batch_rows))
            batch_rows = []
            batch_start = ts
        batch_rows.append(row)
    if batch_rows:
        batches.append(pd.DataFrame(batch_rows))
    for batch in batches:
        on_time, late, max_seen = apply_watermark(
            batch, allowed_lateness_minutes, max_seen)
        on_time_parts.append(on_time)
        late_parts.append(late)
    on_time_all = (pd.concat(on_time_parts, ignore_index=True)
                   if on_time_parts else d.iloc[0:0])
    late_all = (pd.concat(late_parts, ignore_index=True)
                if late_parts else d.iloc[0:0])
    return on_time_all, late_all


def sessionize(df: pd.DataFrame,
               gap_minutes: int = SESSION_GAP_MINUTES) -> pd.DataFrame:
    """Build playback sessions from events (session windows).

    Mirrors Spark session windows with ``gapDuration``: a new session
    starts when the gap between consecutive events for one session_id
    exceeds the gap. Returns one row per session with start, end,
    duration, event count, max playhead and error count.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "session_id", "user_id", "title_id", "device", "region", "app",
            "session_start", "session_end", "duration_seconds",
            "event_count", "max_playhead_seconds", "error_count",
        ])
    d = df.sort_values(["session_id", "event_ts"]).copy()
    d["prev_ts"] = d.groupby("session_id")["event_ts"].shift(1)
    gap = (d["event_ts"] - d["prev_ts"]).dt.total_seconds()
    d["new_session"] = (gap.isna() | (gap > gap_minutes * 60)).astype(int)
    d["window_id"] = d.groupby("session_id")["new_session"].cumsum()
    rows = []
    for (sid, wid), g in d.groupby(["session_id", "window_id"]):
        first = g.iloc[0]
        rows.append({
            "session_id": sid,
            "user_id": first["user_id"],
            "title_id": first["title_id"],
            "device": first["device"],
            "region": first["region"],
            "app": first["app"],
            "session_start": g["event_ts"].min(),
            "session_end": g["event_ts"].max(),
            "duration_seconds": round(
                (g["event_ts"].max() - g["event_ts"].min()).total_seconds(), 1),
            "event_count": len(g),
            "max_playhead_seconds": float(g["playhead_seconds"].max()),
            "error_count": int((g["event_type"] == "error").sum()),
        })
    return pd.DataFrame(rows)


def tumbling_aggregates(df: pd.DataFrame,
                        window_minutes: int = 15) -> pd.DataFrame:
    """15-minute tumbling-window aggregates per title.

    Mirrors ``groupBy(window("event_ts", "15 minutes"), "title_id")``:
    plays (session_start count), distinct sessions, mean bitrate and
    error count per window per title.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "window_start", "title_id", "plays", "distinct_sessions",
            "avg_bitrate_kbps", "error_count",
        ])
    d = df.copy()
    d["window_start"] = d["event_ts"].dt.floor(f"{window_minutes}min")
    agg = (
        d.groupby(["window_start", "title_id"])
        .agg(plays=("event_type", lambda s: int((s == "session_start").sum())),
             distinct_sessions=("session_id", "nunique"),
             avg_bitrate_kbps=("bitrate_kbps",
                               lambda s: round(float(s[s > 0].mean()) if (s > 0).any() else 0.0, 1)),
             error_count=("event_type", lambda s: int((s == "error").sum())))
        .reset_index()
    )
    return agg
