"""Partner onboarding: launch a new integration from spec + sample data.

Before a partner goes live, their spec (field map, timestamp format,
temperature unit, source shape) and a sample of their data are checked
against the shared models in a dry run — nothing loads. The launch
readiness report says go or no-go, with the exact reasons, so a bad spec
never reaches production and a one-off implementation becomes a reusable,
configuration-driven pipeline instead.
"""

from __future__ import annotations

from .normalize import (normalize_milestones, normalize_orders,
                        normalize_telemetry)

# Shared-model fields each feed kind must map to. A spec that misses one
# can never produce a complete shared record, so it cannot launch.
REQUIRED_TARGETS = {
    "device_telemetry": {"reading_id", "shipment_id", "device_id",
                         "recorded_at", "temperature_c"},
    "carrier_milestones": {"milestone_id", "shipment_id", "carrier",
                           "event", "event_at", "location"},
    "customer_orders": {"order_id", "customer", "origin", "destination",
                        "product", "min_temp_c", "max_temp_c", "ship_date",
                        "carrier"},
}

TEMP_UNITS = {"C", "F"}
# A launch is blocked when more than 5% of the sample fails to map.
MAX_FAILURE_RATE = 0.05


def validate_partner_spec(spec: dict, feed_kind: str) -> list:
    """Check a partner spec against the shared model. Returns problems."""
    problems = []
    if feed_kind not in REQUIRED_TARGETS:
        return [f"unknown feed kind {feed_kind!r}; expected one of "
                f"{sorted(REQUIRED_TARGETS)}"]
    if not spec.get("name"):
        problems.append("spec needs a partner name")
    field_map = spec.get("field_map")
    if not isinstance(field_map, dict) or not field_map:
        problems.append("spec needs a non-empty field_map")
        return problems
    mapped = set(field_map.values())
    missing = REQUIRED_TARGETS[feed_kind] - mapped
    if missing:
        problems.append(
            f"field_map misses required targets: {sorted(missing)}")
    if len(mapped) != len(field_map):
        problems.append("field_map maps two source fields to one target")
    temp_unit = spec.get("temp_unit", "C")
    if temp_unit not in TEMP_UNITS:
        problems.append(f"temp_unit must be one of {sorted(TEMP_UNITS)}")
    return problems


def dry_run_sample(spec: dict, feed_kind: str, sample_rows: list[dict]) -> dict:
    """Map sample rows through the normalizer without loading anything.

    Returns per-row outcomes: how many mapped, which rows failed and why,
    and which source fields the spec leaves unmapped.
    """
    normalizer = {
        "device_telemetry": normalize_telemetry,
        "carrier_milestones": normalize_milestones,
        "customer_orders": normalize_orders,
    }[feed_kind]
    mapped = 0
    failures = []
    seen_source_fields: set[str] = set()
    for index, row in enumerate(sample_rows):
        seen_source_fields.update(row.keys())
        try:
            normalizer([row], spec)
            mapped += 1
        except (KeyError, ValueError, TypeError) as exc:
            failures.append({"row": index, "error": str(exc)})
    mapped_sources = set(spec.get("field_map", {}).keys())
    return {
        "rows": len(sample_rows),
        "mapped": mapped,
        "failed": len(failures),
        "failures": failures,
        "unmapped_source_fields": sorted(seen_source_fields - mapped_sources),
    }


def launch_readiness(spec: dict, feed_kind: str, sample_rows: list[dict]) -> dict:
    """Go / no-go for launching a partner, with the exact reasons."""
    problems = validate_partner_spec(spec, feed_kind)
    if problems:
        return {"ready": False, "reasons": problems, "dry_run": None}
    if not sample_rows:
        return {"ready": False,
                "reasons": ["sample data is empty; send sample rows first"],
                "dry_run": None}
    dry_run = dry_run_sample(spec, feed_kind, sample_rows)
    failure_rate = dry_run["failed"] / dry_run["rows"] if dry_run["rows"] else 1.0
    reasons = []
    if failure_rate > MAX_FAILURE_RATE:
        reasons.append(
            f"sample failure rate {failure_rate:.0%} exceeds "
            f"{MAX_FAILURE_RATE:.0%} ({dry_run['failed']} of "
            f"{dry_run['rows']} rows failed to map)")
    if dry_run["unmapped_source_fields"]:
        reasons.append(
            "sample has fields the spec does not map: "
            f"{dry_run['unmapped_source_fields']}")
    return {"ready": not reasons, "reasons": reasons, "dry_run": dry_run}
