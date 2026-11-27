from signals.ingest import ingest_batch
from signals.models import Consent
from signals.realtime import merge_signals, realtime_signals
from tests.conftest import NOW, raw_event


def _events():
    raw = [
        raw_event("e1", ts="2026-11-26T11:30:00",
                  payload={"workflow": "draft-email", "feature": "draft",
                           "goal": "writing", "duration_seconds": 60}),
        raw_event("e2", ts="2026-11-26T11:45:00",
                  payload={"workflow": "draft-email", "feature": "draft",
                           "goal": "writing", "duration_seconds": 60}),
        raw_event("e3", ts="2026-11-26T08:00:00",
                  payload={"workflow": "plan-day", "feature": "schedule",
                           "goal": "productivity", "duration_seconds": 30}),
    ]
    accepted, _ = ingest_batch(raw, set(), now=NOW)
    return accepted


def test_recent_events_scored_stale_ignored(consent):
    signals = realtime_signals("user-01", _events(), consent, "r1", NOW)
    assert [s.value for s in signals] == ["draft"]
    assert signals[0].score == 1.0


def test_empty_window_returns_no_signals(consent):
    signals = realtime_signals("user-99", _events(), consent, "r1", NOW)
    assert signals == []


def test_merge_prefers_higher_score_and_realtime():
    from signals.models import Signal
    batch = [Signal("user-01", "preferred_feature", "usage", "draft", 0.75,
                    "batch", ["e1"], "r1")]
    realtime = [Signal("user-01", "preferred_feature", "usage", "draft", 0.9,
                       "realtime", ["e1"], "r1")]
    merged = merge_signals(batch, realtime)
    assert len(merged) == 1
    assert merged[0].score == 0.9 and merged[0].source == "realtime"


def test_merge_keeps_distinct_values():
    from signals.models import Signal
    batch = [Signal("user-01", "preferred_feature", "usage", "draft", 0.75,
                    "batch", ["e1"], "r1")]
    realtime = [Signal("user-01", "realtime_interest", "usage", "schedule", 0.5,
                       "realtime", ["e3"], "r1")]
    assert len(merge_signals(batch, realtime)) == 2


def test_opted_out_user_gets_no_realtime_signals():
    consent = Consent(user_id="user-01", usage=False)
    assert realtime_signals("user-01", _events(), consent, "r1", NOW) == []
