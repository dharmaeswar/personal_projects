"""Data-quality rules for home-health visits.

Six rules, each returning a reason when it fails. A record that fails any
rule is quarantined with every rule that caught it; nothing invalid reaches
the warehouse. The rules mirror the checks a Snowflake load would enforce
with constraints and a validation step before MERGE.
"""

from __future__ import annotations

from datetime import date

MIN_DURATION_MIN = 5
MAX_DURATION_MIN = 480
MIN_SCORE = 0
MAX_SCORE = 100


def check_visit_date(record: dict, today: date | None = None) -> str | None:
    """Visit date must be present, parseable, and not in the future."""
    raw = (record.get("visit_date") or "").strip()
    if not raw:
        return "missing visit_date"
    try:
        year, month, day = (int(part) for part in raw.split("-"))
        visit = date(year, month, day)
    except (ValueError, TypeError):
        return f"visit_date '{raw}' is not a YYYY-MM-DD date"
    if today is not None and visit > today:
        return f"visit_date {raw} is in the future"
    return None


def check_duration(record: dict) -> str | None:
    """Duration must be an integer within 5-480 minutes."""
    value = record.get("duration_min")
    if not isinstance(value, int) or isinstance(value, bool):
        return f"duration_min '{value}' is not an integer"
    if value < MIN_DURATION_MIN or value > MAX_DURATION_MIN:
        return (
            f"duration_min {value} outside "
            f"{MIN_DURATION_MIN}-{MAX_DURATION_MIN} minutes"
        )
    return None


def check_clinician(record: dict) -> str | None:
    """Clinician id must be present."""
    if not (record.get("clinician_id") or "").strip():
        return "missing clinician_id"
    return None


def check_patient_key(record: dict) -> str | None:
    """Patient key must be present."""
    if not (record.get("patient_key") or "").strip():
        return "missing patient_key"
    return None


def check_assessment_score(record: dict) -> str | None:
    """Assessment score must be an integer within 0-100."""
    value = record.get("assessment_score")
    if not isinstance(value, int) or isinstance(value, bool):
        return f"assessment_score '{value}' is not an integer"
    if value < MIN_SCORE or value > MAX_SCORE:
        return (
            f"assessment_score {value} outside {MIN_SCORE}-{MAX_SCORE}"
        )
    return None


RULES = (
    check_visit_date,
    check_duration,
    check_clinician,
    check_patient_key,
    check_assessment_score,
)


def validate_visits(
    records: list[dict], today: date | None = None
) -> tuple[list[dict], list[dict]]:
    """Split records into (valid, quarantined).

    Quarantined rows carry ``_quarantine_reasons`` (every rule that failed)
    and ``_source``. Duplicate visit ids are quarantined too: the first
    occurrence is kept, later ones are rejected.
    """
    valid: list[dict] = []
    quarantined: list[dict] = []
    seen_ids: set[str] = set()
    for record in records:
        reasons: list[str] = []
        for rule in RULES:
            if rule is check_visit_date:
                reason = rule(record, today)
            else:
                reason = rule(record)
            if reason:
                reasons.append(reason)
        visit_id = (record.get("visit_id") or "").strip()
        if not visit_id:
            reasons.append("missing visit_id")
        elif visit_id in seen_ids:
            reasons.append(f"duplicate visit_id {visit_id}")
        else:
            seen_ids.add(visit_id)
        if reasons:
            bad = dict(record)
            bad["_quarantine_reasons"] = reasons
            quarantined.append(bad)
        else:
            valid.append(record)
    return valid, quarantined
