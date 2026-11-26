"""Data-quality gates for raw interaction events.

Mirrors the bronze -> silver cleansing step of a Databricks job: contract
checks on every row, bad rows quarantined with a reason (never dropped
silently), and exactly-once dedupe on ``event_id``.

Spark equivalents: ``df.filter(...)`` for the rules, ``dropDuplicates(["event_id"])``
after ordering by ``ingested_at``, and a quarantine Delta table for failures.
"""

from __future__ import annotations

import pandas as pd

from .events import EVENT_TYPES

REQUIRED_FIELDS = [
    "event_id", "user_id", "content_id", "event_type",
    "event_ts", "device", "surface", "genre", "content_duration_s",
]


def validate_row(row: pd.Series) -> list[str]:
    """Return the list of quality failures for one event row (empty = clean)."""
    reasons: list[str] = []
    for field in REQUIRED_FIELDS:
        value = row.get(field)
        if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
            reasons.append(f"missing_{field}")
    if row.get("event_type") not in EVENT_TYPES:
        reasons.append("unknown_event_type")
    duration = row.get("content_duration_s")
    watch = row.get("watch_seconds")
    if watch is not None and not pd.isna(watch):
        if watch < 0:
            reasons.append("negative_watch_seconds")
        if duration is not None and not pd.isna(duration) and watch > duration:
            reasons.append("watch_exceeds_duration")
    if duration is not None and not pd.isna(duration) and duration <= 0:
        reasons.append("non_positive_duration")
    return reasons


def cleanse(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split raw events into (clean, quarantined) frames.

    Quarantined rows carry a ``quarantine_reason`` column. Clean rows are
    deduplicated on ``event_id``, keeping the latest ``ingested_at``.
    """
    if df.empty:
        return df.copy(), df.copy()
    reasons = df.apply(validate_row, axis=1)
    bad_mask = reasons.map(bool)
    quarantined = df[bad_mask].copy()
    quarantined["quarantine_reason"] = reasons[bad_mask].map(lambda rs: ";".join(rs))
    clean = df[~bad_mask].copy()
    clean = clean.sort_values("ingested_at").drop_duplicates("event_id", keep="last")
    return clean.reset_index(drop=True), quarantined.reset_index(drop=True)


def quality_report(clean: pd.DataFrame, quarantined: pd.DataFrame) -> dict:
    """Summarise a cleanse run: counts and the top quarantine reasons."""
    total = len(clean) + len(quarantined)
    reason_counts: dict[str, int] = {}
    if not quarantined.empty:
        for reasons in quarantined["quarantine_reason"]:
            for reason in reasons.split(";"):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "total_rows": total,
        "clean_rows": len(clean),
        "quarantined_rows": len(quarantined),
        "quarantine_rate": round(len(quarantined) / total, 4) if total else 0.0,
        "reason_counts": reason_counts,
    }
