from signals.models import Consent, Signal
from signals.privacy import category_of, consented_events, filter_by_consent, redact_payload
from signals.ingest import ingest_batch
from tests.conftest import NOW, raw_event


def _signal(category):
    return Signal("user-01", "preferred_feature", category, "draft", 0.8,
                  "batch", ["e1"], "r1")


def test_filter_drops_opted_out_category():
    consent = Consent(user_id="user-01", telemetry=False)
    kept = filter_by_consent([_signal("usage"), _signal("telemetry")], consent)
    assert [s.category for s in kept] == ["usage"]


def test_filter_keeps_all_when_consented():
    consent = Consent(user_id="user-01")
    assert len(filter_by_consent([_signal("usage"), _signal("telemetry")], consent)) == 2


def test_redact_removes_pii_fields():
    payload = {"feature": "draft", "email": "a@b.com", "free_text": "hello",
               "raw_prompt": "secret"}
    assert redact_payload(payload) == {"feature": "draft"}


def test_category_mapping():
    assert category_of("telemetry") == "telemetry"
    assert category_of("product_usage") == "usage"
    assert category_of("experimentation") == "experimentation"


def test_consented_events_drops_opted_out_type():
    events, _ = ingest_batch(
        [raw_event("e1"), raw_event("e2", event_type="telemetry")], set(), now=NOW)
    consent = Consent(user_id="user-01", telemetry=False)
    kept = consented_events(events, consent)
    assert [e.event_id for e in kept] == ["e1"]
