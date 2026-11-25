"""Tests for data contracts: schema evolution, completeness, freshness."""

from marketintel.contracts import (
    DataContract,
    check_batch,
    check_schema_evolution,
)

CONTRACT = DataContract(
    name="market_snapshot",
    required_fields=["competitor", "zone", "snapshot_date", "price_usd"],
    optional_fields=["demand_index", "service"],
    freshness_hours=24.0,
    min_completeness=0.90,
)

GOOD_ROWS = [
    {"competitor": "lyft", "zone": "downtown", "snapshot_date": "2026-11-24",
     "price_usd": 17.25},
    {"competitor": "via", "zone": "airport", "snapshot_date": "2026-11-24",
     "price_usd": 30.50},
]


def test_good_batch_passes_contract():
    report = check_batch(CONTRACT, GOOD_ROWS, as_of="2026-11-25T00:00:00")
    assert report.errors == []
    assert report.completeness == 1.0


def test_completeness_below_floor_is_error():
    rows = GOOD_ROWS + [{"competitor": "lyft", "zone": "downtown",
                         "snapshot_date": "2026-11-24", "price_usd": None}]
    report = check_batch(CONTRACT, rows, as_of="2026-11-25T00:00:00")
    assert report.completeness < 0.90
    assert any("completeness" in e for e in report.errors)


def test_removed_required_field_is_breaking():
    breaking, additive = check_schema_evolution(
        ["competitor", "zone", "snapshot_date", "price_usd"],
        ["competitor", "zone", "snapshot_date"],
        CONTRACT.required_fields,
    )
    assert breaking == ["price_usd"]
    assert additive == []


def test_new_optional_field_is_additive_not_breaking():
    breaking, additive = check_schema_evolution(
        ["competitor", "zone", "snapshot_date", "price_usd"],
        ["competitor", "zone", "snapshot_date", "price_usd", "surge_multiplier"],
        CONTRACT.required_fields,
    )
    assert breaking == []
    assert additive == ["surge_multiplier"]


def test_breaking_change_reported_in_batch_check():
    report = check_batch(
        CONTRACT, GOOD_ROWS, as_of="2026-11-25T00:00:00",
        previous_fields=["competitor", "zone", "snapshot_date", "price_usd"],
        current_fields=["competitor", "zone", "snapshot_date"],
    )
    assert report.breaking_changes == ["price_usd"]
    assert any("breaking" in e for e in report.errors)
