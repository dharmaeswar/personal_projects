"""Contract validation tests."""
from src.contracts import validate_batch, validate_record

GOOD_EVENT = {
    "event_id": "EVT-1", "account_id": "ACCT-1001", "service_code": "COMPUTE",
    "service_name": "Compute Service", "tier": "standard", "pricing_model": "on-demand",
    "region_code": "us-east-1", "usage_date": "2026-11-03",
    "usage_qty": 10.0, "cost_usd": 4.2, "unit": "vCPU-hours",
}
GOOD_ACCOUNT = {"account_id": "ACCT-1001", "account_name": "Checkout",
                "account_type": "production", "owner_team": "payments",
                "created_date": "2024-01-15"}
GOOD_REGION = {"region_code": "us-east-1", "region_name": "US East", "country": "United States"}


def test_valid_event_passes():
    assert validate_record("service_usage_events", GOOD_EVENT) == []


def test_valid_account_and_region_pass():
    assert validate_record("account_metadata", GOOD_ACCOUNT) == []
    assert validate_record("region_metadata", GOOD_REGION) == []


def test_missing_required_field_rejected():
    bad = {k: v for k, v in GOOD_EVENT.items() if k != "cost_usd"}
    reasons = validate_record("service_usage_events", bad)
    assert any("cost_usd" in r for r in reasons)


def test_negative_usage_rejected():
    assert any("negative" in r for r in validate_record(
        "service_usage_events", {**GOOD_EVENT, "usage_qty": -1}))


def test_negative_cost_rejected():
    assert any("negative" in r for r in validate_record(
        "service_usage_events", {**GOOD_EVENT, "cost_usd": -0.01}))


def test_bad_date_rejected():
    assert validate_record("service_usage_events", {**GOOD_EVENT, "usage_date": "2026-13-40"})
    assert validate_record("service_usage_events", {**GOOD_EVENT, "usage_date": "11/03/2026"})


def test_bad_service_code_and_region_rejected():
    assert validate_record("service_usage_events", {**GOOD_EVENT, "service_code": "compute!"})
    assert validate_record("service_usage_events", {**GOOD_EVENT, "region_code": "USEAST1"})


def test_unknown_tier_pricing_unit_rejected():
    assert validate_record("service_usage_events", {**GOOD_EVENT, "tier": "ultra"})
    assert validate_record("service_usage_events", {**GOOD_EVENT, "pricing_model": "free"})
    assert validate_record("service_usage_events", {**GOOD_EVENT, "unit": "widgets"})


def test_unknown_feed_and_non_dict_rejected():
    assert validate_record("no_such_feed", GOOD_EVENT)
    assert validate_record("service_usage_events", ["not", "a", "dict"])


def test_validate_batch_splits_valid_and_quarantined():
    valid, quarantined = validate_batch(
        "service_usage_events", [GOOD_EVENT, {**GOOD_EVENT, "event_id": "EVT-2", "cost_usd": -5}])
    assert len(valid) == 1 and len(quarantined) == 1
    assert quarantined[0]["record"]["event_id"] == "EVT-2"
    assert quarantined[0]["reasons"]  # reasons are recorded, not dropped silently


def test_zero_usage_is_valid():
    assert validate_record("service_usage_events", {**GOOD_EVENT, "usage_qty": 0, "cost_usd": 0}) == []
