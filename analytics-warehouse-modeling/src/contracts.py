"""Data contracts for the three source feeds.

Each feed has a JSON-schema-like contract (plain dicts, stdlib only).
A contract states: required fields, expected Python types, allowed
values / ranges, and the date format. Nothing here claims an AWS
service: these are local JSON feeds standing in for source files.
"""
from __future__ import annotations

import re
from datetime import date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SERVICE_CODE_RE = re.compile(r"^[A-Z][A-Za-z0-9-]{1,31}$")
REGION_CODE_RE = re.compile(r"^[a-z]{2}-[a-z]+-\d$")

# Allowed values are deliberately small and explicit so a typo in a
# source feed is a contract violation, not silent bad data.
SERVICE_TIERS = {"standard", "premium", "enterprise"}
PRICING_MODELS = {"on-demand", "reserved", "spot"}
ACCOUNT_TYPES = {"production", "development", "sandbox"}
UNITS = {"GB", "hours", "requests", "vCPU-hours"}

CONTRACTS = {
    "service_usage_events": {
        "required": {
            "event_id": str,
            "account_id": str,
            "service_code": str,
            "region_code": str,
            "usage_date": str,
            "usage_qty": (int, float),
            "cost_usd": (int, float),
            "unit": str,
        },
        "optional": {"service_name": str, "tier": str, "pricing_model": str},
    },
    "account_metadata": {
        "required": {
            "account_id": str,
            "account_name": str,
            "account_type": str,
            "owner_team": str,
            "created_date": str,
        },
        "optional": {},
    },
    "region_metadata": {
        "required": {
            "region_code": str,
            "region_name": str,
            "country": str,
        },
        "optional": {},
    },
}


def _is_valid_date(value: str) -> bool:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_record(feed: str, record: dict) -> list[str]:
    """Validate one record against its feed contract.

    Returns a list of violation reasons; empty list means valid.
    Unknown feeds and non-dict records are violations, not crashes.
    """
    if feed not in CONTRACTS:
        return [f"unknown feed: {feed}"]
    if not isinstance(record, dict):
        return ["record is not an object"]
    contract = CONTRACTS[feed]
    reasons: list[str] = []

    for field, expected in contract["required"].items():
        if field not in record or record[field] is None:
            reasons.append(f"missing required field: {field}")
            continue
        value = record[field]
        if not isinstance(value, expected) or isinstance(value, bool):
            reasons.append(
                f"field {field}: expected {getattr(expected, '__name__', expected)}, "
                f"got {type(value).__name__}"
            )
            continue
        if isinstance(value, str) and not value.strip():
            reasons.append(f"field {field}: empty string")

    for field, expected in contract.get("optional", {}).items():
        if field in record and record[field] is not None:
            if not isinstance(record[field], expected) or isinstance(record[field], bool):
                reasons.append(f"field {field}: expected {expected.__name__}")

    if feed == "service_usage_events":
        if isinstance(record.get("service_code"), str) and not SERVICE_CODE_RE.match(record["service_code"]):
            reasons.append(f"field service_code: invalid format: {record['service_code']!r}")
        if isinstance(record.get("region_code"), str) and not REGION_CODE_RE.match(record["region_code"]):
            reasons.append(f"field region_code: invalid format: {record['region_code']!r}")
        if not _is_valid_date(str(record.get("usage_date", ""))):
            reasons.append(f"field usage_date: invalid date: {record.get('usage_date')!r}")
        for num_field in ("usage_qty", "cost_usd"):
            v = record.get(num_field)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                reasons.append(f"field {num_field}: negative value {v}")
        if record.get("unit") not in (None, *UNITS) and isinstance(record.get("unit"), str):
            reasons.append(f"field unit: unknown unit: {record['unit']!r}")
        if record.get("tier") is not None and record["tier"] not in SERVICE_TIERS:
            reasons.append(f"field tier: unknown tier: {record['tier']!r}")
        if record.get("pricing_model") is not None and record["pricing_model"] not in PRICING_MODELS:
            reasons.append(f"field pricing_model: unknown pricing model: {record['pricing_model']!r}")

    if feed == "account_metadata":
        if record.get("account_type") not in (None, *ACCOUNT_TYPES) and isinstance(record.get("account_type"), str):
            reasons.append(f"field account_type: unknown type: {record['account_type']!r}")
        if not _is_valid_date(str(record.get("created_date", ""))):
            reasons.append(f"field created_date: invalid date: {record.get('created_date')!r}")

    if feed == "region_metadata":
        if isinstance(record.get("region_code"), str) and not REGION_CODE_RE.match(record["region_code"]):
            reasons.append(f"field region_code: invalid format: {record['region_code']!r}")

    return reasons


def validate_batch(feed: str, records: list[dict]):
    """Split a batch into (valid_records, quarantined).

    Quarantined entries keep the original row plus the violation
    reasons, so bad data is inspectable instead of silently dropped.
    """
    valid, quarantined = [], []
    for record in records:
        reasons = validate_record(feed, record)
        if reasons:
            quarantined.append({"record": record, "reasons": reasons, "feed": feed})
        else:
            valid.append(record)
    return valid, quarantined
