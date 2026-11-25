"""Tests for schema mapping: confidence scores, synonyms, fuzzy
matches, structured-output validation, and the human-review queue."""

from marketintel.schema_mapping import (
    ReviewQueue,
    map_record,
    propose_mapping,
    validate_mapped,
)


def test_exact_match_scores_1():
    mapping, unmapped = propose_mapping(["competitor", "zone", "price_usd"])
    assert mapping["competitor"] == ("competitor", 1.00)
    assert mapping["price_usd"] == ("price_usd", 1.00)
    assert unmapped == []


def test_synonym_rename_scores_085():
    # v2 feed renamed price_usd -> fare_usd; provider -> competitor.
    mapping, _ = propose_mapping(["provider", "area", "day", "fare_usd"])
    assert mapping["fare_usd"] == ("price_usd", 0.85)
    assert mapping["provider"] == ("competitor", 0.85)
    assert mapping["area"] == ("zone", 0.85)
    assert mapping["day"] == ("snapshot_date", 0.85)


def test_fuzzy_match_goes_to_review():
    mapped, report = map_record(
        {"competitor": "via", "zone_name": "university",
         "snapshot_date": "2026-11-24", "price_usd": "12.40"}
    )
    assert mapped["zone"] == "university"
    assert report.field_confidence["zone"] == 0.60
    assert ("zone_name", "zone", 0.60) in report.needs_review
    assert report.ok


def test_unmapped_field_recorded_never_guessed():
    _, report = map_record(
        {"competitor": "lyft", "zone": "downtown",
         "snapshot_date": "2026-11-24", "price_usd": "17.25",
         "internal_notes": "ignore me"}
    )
    assert "internal_notes" in report.unmapped
    assert "internal_notes" not in report.mapped
    assert report.ok


def test_missing_required_field_is_validation_error():
    _, report = map_record(
        {"competitor": "lyft", "zone": "downtown",
         "snapshot_date": "2026-11-24"}
    )
    assert not report.ok
    assert any("price_usd" in e for e in report.validation_errors)


def test_bad_enum_and_negative_price_are_errors():
    errors = validate_mapped(
        {"competitor": "lyft", "zone": "downtown",
         "snapshot_date": "2026-11-24", "price_usd": -5.0,
         "service": "scooter"}
    )
    assert any("price_usd" in e for e in errors)
    assert any("service" in e for e in errors)


def test_non_numeric_price_is_validation_error():
    _, report = map_record(
        {"competitor": "lyft", "zone": "downtown",
         "snapshot_date": "2026-11-24", "price_usd": "abc"}
    )
    assert not report.ok


def test_valid_record_coerces_types():
    mapped, report = map_record(
        {"competitor": "lyft", "zone": "downtown",
         "snapshot_date": "2026-11-24", "price_usd": "17.25",
         "demand_index": "1.4", "service": "ride"}
    )
    assert report.ok
    assert mapped["price_usd"] == 17.25
    assert isinstance(mapped["price_usd"], float)
    assert mapped["demand_index"] == 1.4


def test_review_queue_confirm_stops_requeue():
    queue = ReviewQueue()
    assert queue.add("zone_name", "zone", 0.60, record_ref="demand_api")
    assert len(queue.pending()) == 1
    queue.confirm("zone_name", "zone")
    assert queue.pending() == []
    assert queue.add("zone_name", "zone", 0.60) is False
