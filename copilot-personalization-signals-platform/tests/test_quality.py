from signals.ingest import ingest_batch
from signals.models import Signal
from signals.quality import check_events, check_signals
from tests.conftest import NOW, raw_event


def test_clean_events_pass():
    events, _ = ingest_batch([raw_event()], set(), now=NOW)
    assert check_events(events, NOW) == []


def test_duplicate_ids_flagged():
    from signals.models import Event
    events = [Event("e1", "user-01", "telemetry", "copilot-app", "2026-11-26T10:00:00", {}),
              Event("e1", "user-01", "telemetry", "copilot-app", "2026-11-26T10:00:00", {})]
    assert "duplicate event_id in store" in check_events(events, NOW)


def test_stale_events_flagged():
    events, _ = ingest_batch([raw_event(ts="2026-11-20T10:00:00")], set(), now=NOW)
    assert any("freshness" in p for p in check_events(events, NOW))


def test_signal_score_out_of_range_flagged():
    events, _ = ingest_batch([raw_event()], set(), now=NOW)
    bad = Signal("user-01", "preferred_feature", "usage", "draft", 1.5,
                 "batch", ["evt-1"], "r1")
    assert any("out of range" in p for p in check_signals([bad], events))


def test_signal_without_source_events_flagged():
    events, _ = ingest_batch([raw_event()], set(), now=NOW)
    bad = Signal("user-01", "preferred_feature", "usage", "draft", 0.5,
                 "batch", [], "r1")
    assert any("no source events" in p for p in check_signals([bad], events))


def test_signal_citing_unknown_event_flagged():
    events, _ = ingest_batch([raw_event()], set(), now=NOW)
    bad = Signal("user-01", "preferred_feature", "usage", "draft", 0.5,
                 "batch", ["evt-nope"], "r1")
    assert any("unknown event ids" in p for p in check_signals([bad], events))


def test_valid_signal_passes():
    events, _ = ingest_batch([raw_event()], set(), now=NOW)
    good = Signal("user-01", "preferred_feature", "usage", "draft", 0.5,
                  "batch", ["evt-1"], "r1")
    assert check_signals([good], events) == []
