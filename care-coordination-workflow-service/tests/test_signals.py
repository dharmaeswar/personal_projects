"""Tests for the data-science signal delivery module (care_coord/signals.py)."""

import pytest

from care_coord.service import CareCoordinationService
from care_coord.signals import (
    MAX_DELIVERY_ATTEMPTS,
    SignalDeliveryPipeline,
    backoff_seconds,
    compute_signals,
)


@pytest.fixture
def svc():
    return CareCoordinationService()


@pytest.fixture
def busy_plan(svc):
    """One active plan: 1 open + 1 completed referral, 1 blocked + 1 done task."""
    plan = svc.create_care_plan("PAT-0001", "Follow-up")
    svc.transition_plan(plan.id, "active")
    svc.add_referral(plan.id, "cardiology")
    ref2 = svc.add_referral(plan.id, "radiology")
    svc.transition_referral(ref2.id, "accepted")
    svc.transition_referral(ref2.id, "scheduled")
    svc.transition_referral(ref2.id, "completed")
    task = svc.create_task(plan.id, "Call patient")
    svc.transition_task(task.id, "in_progress")
    svc.transition_task(task.id, "blocked")
    task2 = svc.create_task(plan.id, "Send summary")
    svc.transition_task(task2.id, "in_progress")
    svc.transition_task(task2.id, "done")
    return plan


def _by_name(signals):
    return {s.name: s.value for s in signals}


def test_compute_signals_counts_open_and_blocked(svc, busy_plan):
    values = _by_name(compute_signals(svc.store, "2026-11-25"))
    assert values["open_referral_count"] == 1.0
    assert values["blocked_task_count"] == 1.0


def test_compute_signals_ratios(svc, busy_plan):
    values = _by_name(compute_signals(svc.store, "2026-11-25"))
    assert values["task_completion_ratio"] == 0.5
    assert values["referral_completion_ratio"] == 0.5


def test_compute_signals_risk_score_weights_blocked_tasks(svc, busy_plan):
    values = _by_name(compute_signals(svc.store, "2026-11-25"))
    assert values["coordination_risk_score"] == 1.0 + 2 * 1.0


def test_compute_signals_empty_plan_is_zero_not_error(svc):
    svc.create_care_plan("PAT-0002", "Wellness")
    values = _by_name(compute_signals(svc.store, "2026-11-25"))
    assert values["task_completion_ratio"] == 0.0
    assert values["coordination_risk_score"] == 0.0


def test_compute_signals_carry_window_and_patient_ref(svc, busy_plan):
    signals = compute_signals(svc.store, "2026-11-25")
    assert signals and all(s.window == "2026-11-25" for s in signals)
    assert all(s.patient_ref == "PAT-0001" for s in signals)


def test_run_once_delivers_every_signal(svc, busy_plan):
    received = []
    pipe = SignalDeliveryPipeline(svc.store, received.append, target="feature-store",
                                  sleep=lambda _: None)
    counts = pipe.run_once("2026-11-25")
    assert counts == {"delivered": 5, "duplicate": 0, "failed": 0}
    assert len(received) == 5
    assert all(r.status == "delivered" and r.attempts == 1 for r in pipe.delivery_log)
    assert all(r.target == "feature-store" for r in pipe.delivery_log)


def test_run_once_same_window_is_idempotent(svc, busy_plan):
    received = []
    pipe = SignalDeliveryPipeline(svc.store, received.append, sleep=lambda _: None)
    pipe.run_once("2026-11-25")
    counts = pipe.run_once("2026-11-25")
    assert counts["duplicate"] == 5
    assert len(received) == 5  # nothing delivered twice


def test_new_window_delivers_again(svc, busy_plan):
    received = []
    pipe = SignalDeliveryPipeline(svc.store, received.append, sleep=lambda _: None)
    pipe.run_once("2026-11-25")
    counts = pipe.run_once("2026-11-26")
    assert counts["delivered"] == 5
    assert len(received) == 10


def test_failing_sink_retries_then_logs_failed(svc, busy_plan):
    calls = []

    def bad_sink(signal):
        calls.append(signal)
        raise RuntimeError("sink unavailable")

    pipe = SignalDeliveryPipeline(svc.store, bad_sink, sleep=lambda _: None)
    counts = pipe.run_once("2026-11-25")
    assert counts["failed"] == 5
    assert len(calls) == 5 * MAX_DELIVERY_ATTEMPTS
    failed = pipe.failed_deliveries()
    assert len(failed) == 5
    assert all(r.attempts == MAX_DELIVERY_ATTEMPTS for r in failed)
    assert all("sink unavailable" in r.last_error for r in failed)


def test_flaky_sink_recovers_within_attempts(svc, busy_plan):
    state = {"n": 0}

    def flaky(signal):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("transient")

    pipe = SignalDeliveryPipeline(svc.store, flaky, sleep=lambda _: None)
    counts = pipe.run_once("2026-11-25")
    assert counts["failed"] == 0
    assert counts["delivered"] == 5


def test_backoff_grows_and_caps():
    assert backoff_seconds(1) == 0.1
    assert backoff_seconds(2) == 0.2
    assert backoff_seconds(3) == 0.4
    assert backoff_seconds(20) == 5.0
