"""Data-quality rules over standardized EMR rows.

Every rule is a named check. A row that fails any rule is quarantined
with every rule that caught it — nothing invalid reaches the measures
or the dashboard, and nothing is silently dropped. The quarantine list
is the input to root-cause analysis.

Rules:
- UNKNOWN_ENCOUNTER: child row references an encounter missing from
  the encounter feed (referential integrity).
- FUTURE_TIMESTAMP: a timestamp dated after the run date (source clock
  or timezone problem).
- OUT_OF_RANGE: a vital or lab value outside its plausible clinical
  range, judged in canonical units after standardization.
- DUPLICATE: the same clinical observation sent twice (same encounter,
  same concept, same timestamp).
- RESULT_BEFORE_COLLECTION: a lab result timestamped before its
  collection time.
- INVALID_DOSE: a medication dose of zero/negative, or a dose unit the
  vocabulary does not know.
"""

from datetime import date, datetime

from .standardize import LAB_RANGES, VITAL_RANGES, to_float

RULES = (
    "UNKNOWN_ENCOUNTER",
    "FUTURE_TIMESTAMP",
    "OUT_OF_RANGE",
    "DUPLICATE",
    "RESULT_BEFORE_COLLECTION",
    "INVALID_DOSE",
)


def _parse_dt(text):
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except (TypeError, ValueError):
            continue
    return None


def _is_future(text, run_date):
    dt = _parse_dt(text)
    if dt is None:
        return False
    return dt.date() > run_date


def check_vital(row, encounter_ids, seen, run_date):
    rules = []
    if row.get("encounter_id") not in encounter_ids:
        rules.append("UNKNOWN_ENCOUNTER")
    if _is_future(row.get("recorded_at", ""), run_date):
        rules.append("FUTURE_TIMESTAMP")
    value = to_float(row.get("value"))
    vtype = row.get("vital_type")
    if value is None:
        rules.append("OUT_OF_RANGE")
    elif vtype in VITAL_RANGES:
        low, high = VITAL_RANGES[vtype]
        if not (low <= value <= high):
            rules.append("OUT_OF_RANGE")
    key = (row.get("encounter_id"), vtype, row.get("recorded_at"))
    if key in seen:
        rules.append("DUPLICATE")
    else:
        seen.add(key)
    return rules


def check_lab(row, encounter_ids, seen, run_date):
    rules = []
    if row.get("encounter_id") not in encounter_ids:
        rules.append("UNKNOWN_ENCOUNTER")
    if _is_future(row.get("collected_at", ""), run_date):
        rules.append("FUTURE_TIMESTAMP")
    value = to_float(row.get("result_value"))
    test = row.get("test_name")
    if value is None:
        rules.append("OUT_OF_RANGE")
    elif test in LAB_RANGES:
        low, high = LAB_RANGES[test]
        if not (low <= value <= high):
            rules.append("OUT_OF_RANGE")
    collected = _parse_dt(row.get("collected_at", ""))
    resulted = _parse_dt(row.get("result_at", ""))
    if collected is not None and resulted is not None and resulted < collected:
        rules.append("RESULT_BEFORE_COLLECTION")
    key = (row.get("encounter_id"), test, row.get("collected_at"))
    if key in seen:
        rules.append("DUPLICATE")
    else:
        seen.add(key)
    return rules


def check_medication(row, encounter_ids, seen, run_date):
    rules = []
    if row.get("encounter_id") not in encounter_ids:
        rules.append("UNKNOWN_ENCOUNTER")
    if _is_future(row.get("start_date", ""), run_date):
        rules.append("FUTURE_TIMESTAMP")
    dose = to_float(row.get("dose"))
    from .standardize import KNOWN_DOSE_UNITS
    if dose is None or dose <= 0 or row.get("dose_unit") not in KNOWN_DOSE_UNITS:
        rules.append("INVALID_DOSE")
    return rules


def check_encounter(row, run_date):
    rules = []
    if _is_future(row.get("encounter_date", ""), run_date):
        rules.append("FUTURE_TIMESTAMP")
    return rules


def run_quality(feeds, run_date=None):
    """Run every rule over every feed.

    Returns {"clean": {feed: [rows]}, "quarantined": [{"feed", "row",
    "rules": [...]}]}. ``run_date`` is a datetime.date; defaults to
    2026-11-28 (the run date of this project snapshot).
    """
    run_date = run_date or date(2026, 11, 28)
    encounter_ids = {r.get("encounter_id") for r in feeds.get("encounters", [])}
    clean = {}
    quarantined = []

    for row in feeds.get("encounters", []):
        rules = check_encounter(row, run_date)
        if rules:
            quarantined.append({"feed": "encounters", "row": row, "rules": rules})
        else:
            clean.setdefault("encounters", []).append(row)

    for feed, checker in (("vitals", check_vital), ("labs", check_lab)):
        seen = set()
        kept = []
        for row in feeds.get(feed, []):
            rules = checker(row, encounter_ids, seen, run_date)
            if rules:
                quarantined.append({"feed": feed, "row": row, "rules": rules})
            else:
                kept.append(row)
        clean[feed] = kept

    kept = []
    for row in feeds.get("medications", []):
        rules = check_medication(row, encounter_ids, set(), run_date)
        if rules:
            quarantined.append({"feed": "medications", "row": row, "rules": rules})
        else:
            kept.append(row)
    clean["medications"] = kept
    clean.setdefault("encounters", [])
    return {"clean": clean, "quarantined": quarantined}
