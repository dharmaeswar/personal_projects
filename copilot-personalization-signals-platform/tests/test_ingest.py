from signals.ingest import ingest_batch, retry_quarantined, validate_event
from tests.conftest import NOW, raw_event


def test_valid_event_accepted():
    accepted, quarantined = ingest_batch([raw_event()], set(), now=NOW)
    assert len(accepted) == 1 and quarantined == []


def test_missing_user_quarantined_with_reason():
    accepted, quarantined = ingest_batch([raw_event(user_id="")], set(), now=NOW)
    assert accepted == []
    assert "missing user_id" in quarantined[0]["reasons"]


def test_unknown_event_type_quarantined():
    accepted, quarantined = ingest_batch([raw_event(event_type="mystery")], set(), now=NOW)
    assert accepted == []
    assert any("unknown event_type" in r for r in quarantined[0]["reasons"])


def test_future_timestamp_quarantined():
    accepted, quarantined = ingest_batch(
        [raw_event(ts="2026-11-27T10:00:00")], set(), now=NOW)
    assert accepted == []
    assert "future timestamp" in quarantined[0]["reasons"]


def test_negative_duration_quarantined():
    accepted, quarantined = ingest_batch(
        [raw_event(payload={"duration_seconds": -5})], set(), now=NOW)
    assert accepted == []
    assert "negative duration_seconds" in quarantined[0]["reasons"]


def test_experimentation_needs_known_arm():
    bad = raw_event(event_type="experimentation",
                    payload={"experiment": "exp-a", "experiment_arm": "weird"})
    accepted, quarantined = ingest_batch([bad], set(), now=NOW)
    assert accepted == [] and "unknown experiment_arm" in quarantined[0]["reasons"]
    good = raw_event(event_type="experimentation",
                     payload={"experiment": "exp-a", "experiment_arm": "treatment"})
    accepted, _ = ingest_batch([good], set(), now=NOW)
    assert len(accepted) == 1


def test_duplicate_event_id_collapses_to_one():
    seen = set()
    accepted, _ = ingest_batch([raw_event()], seen, now=NOW)
    accepted2, quarantined = ingest_batch([raw_event()], seen, now=NOW)
    assert len(accepted) == 1 and accepted2 == []
    assert "duplicate event_id" in quarantined[0]["reasons"]


def test_retry_promotes_corrected_row():
    _, quarantined = ingest_batch([raw_event(user_id="")], set(), now=NOW)
    promoted, still_bad = retry_quarantined(
        quarantined, {"evt-1": {"user_id": "user-01"}}, set(), now=NOW)
    assert len(promoted) == 1 and still_bad == []


def test_retry_without_fix_stays_quarantined():
    _, quarantined = ingest_batch([raw_event(user_id="")], set(), now=NOW)
    promoted, still_bad = retry_quarantined(quarantined, {}, set(), now=NOW)
    assert promoted == [] and len(still_bad) == 1


def test_validate_event_bad_timestamp():
    assert "bad timestamp" in validate_event(raw_event(ts="not-a-date"), now=NOW)
