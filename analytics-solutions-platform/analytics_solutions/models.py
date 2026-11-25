"""Requirement-driven dimensional and relational models.

Star schema for policy analytics: ``dim_holder``, ``dim_advisor``,
``dim_date`` and ``fact_policy_activity`` (grain: one activity by one
holder on one day). Surrogate keys are stable within a build; foreign
keys are enforced at load time so a fact row can never point at a
missing dimension row.
"""

from __future__ import annotations

from datetime import date


class DimensionLoadError(ValueError):
    pass


def build_dim_holder(holders: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """SCD Type 1 holder dimension. Returns (rows, natural_key -> surrogate_key)."""
    rows: list[dict] = []
    keys: dict[str, int] = {}
    for i, h in enumerate(sorted(holders, key=lambda r: str(r.get("holder_id"))), start=1):
        holder_id = str(h.get("holder_id") or "").strip()
        if not holder_id:
            raise DimensionLoadError("holder row without holder_id")
        if holder_id in keys:
            raise DimensionLoadError(f"duplicate holder_id: {holder_id}")
        keys[holder_id] = i
        rows.append({
            "holder_key": i,
            "holder_id": holder_id,
            "holder_name": str(h.get("holder_name") or "").strip(),
            "state": str(h.get("state") or "").strip(),
            "segment": str(h.get("segment") or "").strip(),
        })
    return rows, keys


def build_dim_advisor(advisors: list[dict]) -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    keys: dict[str, int] = {}
    for i, a in enumerate(sorted(advisors, key=lambda r: str(r.get("advisor_id"))), start=1):
        advisor_id = str(a.get("advisor_id") or "").strip()
        if not advisor_id:
            raise DimensionLoadError("advisor row without advisor_id")
        if advisor_id in keys:
            raise DimensionLoadError(f"duplicate advisor_id: {advisor_id}")
        keys[advisor_id] = i
        rows.append({
            "advisor_key": i,
            "advisor_id": advisor_id,
            "advisor_name": str(a.get("advisor_name") or "").strip(),
            "office": str(a.get("office") or "").strip(),
        })
    return rows, keys


def build_dim_date(start: date, end: date) -> list[dict]:
    """Calendar dimension, one row per day in [start, end]."""
    from datetime import timedelta
    rows: list[dict] = []
    day = start
    while day <= end:
        rows.append({
            "date_key": int(day.strftime("%Y%m%d")),
            "date": day,
            "year": day.year,
            "month": day.month,
            "day": day.day,
            "weekday": day.weekday(),  # Monday = 0
            "is_month_end": (day + timedelta(days=1)).month != day.month,
        })
        day += timedelta(days=1)
    return rows


def build_fact_policy_activity(policies: list[dict], activity_features: list[dict],
                               holder_keys: dict[str, int],
                               advisor_keys: dict[str, int],
                               as_of: date) -> list[dict]:
    """Fact table, grain: one row per policy, joined to holder/advisor dims.

    Raises DimensionLoadError when a policy references a holder or advisor
    missing from the dimensions — a load failure, not a silent null.
    """
    activity_by_holder = {r["holder_id"]: r for r in activity_features}
    facts: list[dict] = []
    for p in sorted(policies, key=lambda r: r["policy_id"]):
        holder_id = p["holder_id"]
        advisor_id = p["advisor_id"]
        if holder_id not in holder_keys:
            raise DimensionLoadError(f"policy {p['policy_id']} references unknown holder {holder_id}")
        if advisor_id not in advisor_keys:
            raise DimensionLoadError(f"policy {p['policy_id']} references unknown advisor {advisor_id}")
        feats = activity_by_holder.get(holder_id, {"activity_count_30d": 0,
                                                   "days_since_last_activity": None})
        facts.append({
            "policy_id": p["policy_id"],
            "holder_key": holder_keys[holder_id],
            "advisor_key": advisor_keys[advisor_id],
            "date_key": int(as_of.strftime("%Y%m%d")),
            "product": p["product"],
            "premium_annual": p["premium_annual"],
            "premium_band": p["premium_band"],
            "tenure_days": p["tenure_days"],
            "is_active": p["is_active"],
            "activity_count_30d": feats["activity_count_30d"],
            "days_since_last_activity": feats["days_since_last_activity"],
        })
    return facts
