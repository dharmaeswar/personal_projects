"""Tests for the outbox dispatcher: retries, backoff, idempotency, dead-lettering."""

import pytest

from care_coord.events import Dispatcher, backoff_seconds
from care_coord.models import Event
from care_coord.service import CareCoordinationService
from care_coord.store import Store


@pytest.fixture
def store():
    return Store()


def test_backoff_grows_exponentially():
    assert backoff_seconds(1) == pytest.approx(0.1)
    assert backoff_seconds(2) == pytest.approx(0.2)
    assert backoff_seconds(3) == pytest.approx(0.4)
    assert backoff_seconds(10) == pytest.approx(5.0)  # capped


def test_dispatch_delivers_and_marks_done(store):
    seen = []
    event = Event(event_type="task.created", aggregate_id="t1")
    store.enqueue(event)
    d = Dispatcher(store, sleep=lambda s: None)
    assert d.dispatch_one(event, lambda e: seen.append(e.id)) == "delivered"
    assert seen == [event.id]
    assert event.delivered is True
    assert event.attempts == 1


def test_dispatch_retries_on_failure_then_succeeds(store):
    calls = {"n": 0}

    def flaky(event):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("downstream unavailable")

    event = Event(event_type="referral.requested", aggregate_id="r1")
    store.enqueue(event)
    d = Dispatcher(store, sleep=lambda s: None)
    assert d.dispatch_one(event, flaky) == "retry"
    assert d.dispatch_one(event, flaky) == "retry"
    assert d.dispatch_one(event, flaky) == "delivered"
    assert calls["n"] == 3
    assert event.attempts == 3


def test_dispatch_dead_letters_after_max_attempts(store):
    def always_fail(event):
        raise RuntimeError("boom")

    event = Event(event_type="care_plan.created", aggregate_id="p1")
    store.enqueue(event)
    d = Dispatcher(store, sleep=lambda s: None)
    assert d.dispatch_one(event, always_fail) == "retry"
    assert d.dispatch_one(event, always_fail) == "retry"
    assert d.dispatch_one(event, always_fail) == "failed"
    assert event.delivered is True  # marked so it stops being retried
    assert event.attempts == 3


def test_duplicate_delivery_is_skipped(store):
    seen = []
    event = Event(event_type="task.created", aggregate_id="t1")
    store.enqueue(event)
    d = Dispatcher(store, sleep=lambda s: None)
    assert d.dispatch_one(event, lambda e: seen.append(1)) == "delivered"
    # Redeliver the same event object (e.g. after a crash/replay).
    event.delivered = False
    assert d.dispatch_one(event, lambda e: seen.append(1)) == "duplicate"
    assert seen == [1]


def test_dispatch_all_drains_outbox():
    svc = CareCoordinationService()
    svc.create_care_plan("PAT-0001", "Follow-up")
    svc.create_care_plan("PAT-0002", "Check-up")
    seen = []
    counts = svc.process_outbox(lambda e: seen.append(e.event_type))
    assert counts["delivered"] == 2
    assert counts["duplicate"] == 0
    assert svc.store.pending_events() == []


def test_handler_failure_does_not_mark_key_processed(store):
    def failing(event):
        raise RuntimeError("nope")

    event = Event(event_type="task.created", aggregate_id="t1")
    store.enqueue(event)
    d = Dispatcher(store, sleep=lambda s: None)
    assert d.dispatch_one(event, failing) == "retry"
    assert event.idempotency_key not in store.processed_keys
