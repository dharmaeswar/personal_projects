"""Cleansing and feature engineering.

Cleansing is explicit and auditable: every dropped or quarantined row is
named with a reason, never silently discarded. Feature engineering adds the
derived columns analysts consume downstream (tenure, premium band,
recency, rolling activity).
"""

from __future__ import annotations

from datetime import date


def _to_float(value, field: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def cleanse_policy_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Cleanse raw policy rows.

    Returns ``(clean, quarantined)``. A row is quarantined (with a reason)
    when it has no usable policy id, a non-numeric or negative premium, or
    an unparseable effective date. Clean rows get typed fields.
    """
    clean: list[dict] = []
    quarantined: list[dict] = []
    for row in rows:
        policy_id = str(row.get("policy_id") or "").strip()
        if not policy_id:
            quarantined.append({**row, "_quarantine_reason": "missing policy_id"})
            continue
        premium = _to_float(row.get("premium_annual"), "premium_annual")
        if premium is None or premium < 0:
            quarantined.append({**row, "_quarantine_reason": "bad premium_annual"})
            continue
        effective = _to_date(row.get("effective_date"))
        if effective is None:
            quarantined.append({**row, "_quarantine_reason": "bad effective_date"})
            continue
        clean.append({
            "policy_id": policy_id,
            "holder_id": str(row.get("holder_id") or "").strip(),
            "advisor_id": str(row.get("advisor_id") or "").strip(),
            "product": str(row.get("product") or "").strip(),
            "premium_annual": premium,
            "effective_date": effective,
            "status": str(row.get("status") or "active").strip().lower(),
        })
    return clean, quarantined


def dedupe_by_key(rows: list[dict], key: str) -> tuple[list[dict], list[dict]]:
    """Keep the first row per key; later duplicates are returned separately."""
    seen: set = set()
    kept: list[dict] = []
    dupes: list[dict] = []
    for row in rows:
        k = row.get(key)
        if k in seen:
            dupes.append(row)
        else:
            seen.add(k)
            kept.append(row)
    return kept, dupes


def premium_band(premium: float) -> str:
    if premium < 1_000:
        return "under_1k"
    if premium < 5_000:
        return "1k_5k"
    if premium < 25_000:
        return "5k_25k"
    return "25k_plus"


def engineer_policy_features(clean_rows: list[dict], as_of: date) -> list[dict]:
    """Add derived features analysts consume: tenure and premium band."""
    out: list[dict] = []
    for row in clean_rows:
        tenure_days = (as_of - row["effective_date"]).days
        out.append({
            **row,
            "tenure_days": tenure_days,
            "premium_band": premium_band(row["premium_annual"]),
            "is_active": row["status"] == "active",
        })
    return out


def engineer_activity_features(activity_rows: list[dict], as_of: date,
                                window_days: int = 30) -> list[dict]:
    """Add recency and rolling-window activity counts per holder.

    Input rows: ``{"holder_id", "activity_date", "activity_type"}``.
    Output: one row per holder with ``activity_count_30d`` and
    ``days_since_last_activity``.
    """
    by_holder: dict[str, list[date]] = {}
    for row in activity_rows:
        d = _to_date(row.get("activity_date"))
        if d is None:
            continue
        by_holder.setdefault(str(row.get("holder_id") or ""), []).append(d)
    out: list[dict] = []
    for holder_id, dates in sorted(by_holder.items()):
        recent = [d for d in dates if 0 <= (as_of - d).days <= window_days]
        out.append({
            "holder_id": holder_id,
            "activity_count_30d": len(recent),
            "days_since_last_activity": (as_of - max(dates)).days,
            "total_activities": len(dates),
        })
    return out
