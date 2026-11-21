"""Tests for instrumentation contracts."""
from product_analytics.contracts import validate_batch, validate_event


def good_event(**overrides):
    event = {
        "event_id": "e1",
        "user_id": "u1",
        "event_type": "pin_save",
        "event_ts": "2026-11-03T10:00:00",
        "payload": {"pin_id": "pin_1", "board_id": "recipes"},
    }
    event.update(overrides)
    return event


def test_valid_event_has_no_violations():
    assert validate_event(good_event()) == []


def test_missing_required_field_is_violation():
    violations = validate_event(good_event(user_id=""))
    assert any("user_id" in v.reason for v in violations)


def test_unknown_event_type_is_violation():
    violations = validate_event(good_event(event_type="mystery"))
    assert any("unknown event_type" in v.reason for v in violations)


def test_missing_nested_payload_key_is_violation():
    violations = validate_event(good_event(payload={"pin_id": "pin_1"}))
    assert any("board_id" in v.reason for v in violations)


def test_payload_as_json_string_is_checked():
    event = good_event(payload='{"pin_id": "pin_1"}')
    assert any("board_id" in v.reason for v in validate_event(event))


def test_batch_split_keeps_good_and_bad_separate():
    good, bad = validate_batch([good_event(), good_event(event_id="e2", user_id="")])
    assert [g["event_id"] for g in good] == ["e1"]
    assert len(bad) == 1
