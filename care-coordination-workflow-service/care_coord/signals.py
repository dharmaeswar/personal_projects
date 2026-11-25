"""Data-science signal delivery: scheduled signals from care events.

This module is the data-pipeline side of the service. On a schedule (the
caller decides the cadence; ``run_once`` is one scheduled tick) it reads
the care events and aggregates already in the store, computes a small set
of delivery-ready signals per care plan — the kind of features a data
science consumer would use to prioritise outreach — and delivers each
signal to a downstream sink.

Delivery mirrors the outbox rules used elsewhere in this project:

- every delivery attempt is written to a delivery log (signal, target,
  attempt count, outcome, error), so a missed delivery is visible, not
  silent;
- a failing sink is retried with exponential backoff up to a bounded
  number of attempts, then the delivery is marked ``failed`` in the log
  instead of being retried forever;
- delivery is idempotent per (signal name, plan, window): re-running the
  same scheduled window does not deliver the same signal twice.

All inputs are the service's synthetic, de-identified aggregates
(opaque ``PAT-####`` references and counts). No real health data, no
network access in the computation itself; the sink is a caller-supplied
callable, so tests use an in-memory sink.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .models import ReferralStatus, TaskStatus, new_id, now_iso
from .store import Store

MAX_DELIVERY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.1

TERMINAL_REFERRAL = {ReferralStatus.COMPLETED, ReferralStatus.DECLINED, ReferralStatus.CANCELLED}
TERMINAL_TASK = {TaskStatus.DONE, TaskStatus.CANCELLED}


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 0.1s, 0.2s, 0.4s, ... capped at 5s."""
    return min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), 5.0)


@dataclass
class Signal:
    """One computed signal, ready for delivery to a data-science consumer."""

    id: str = field(default_factory=new_id)
    name: str = ""
    plan_id: str = ""
    patient_ref: str = ""
    value: float = 0.0
    window: str = ""
    computed_at: str = field(default_factory=now_iso)

    @property
    def delivery_key(self) -> str:
        """Idempotency key: one delivery per signal/plan/window."""
        return f"{self.name}:{self.plan_id}:{self.window}"


@dataclass
class DeliveryRecord:
    """One row of the delivery log: what was sent, where, and how it ended."""

    id: str = field(default_factory=new_id)
    signal_id: str = ""
    delivery_key: str = ""
    target: str = ""
    status: str = "pending"  # pending -> delivered | failed | duplicate
    attempts: int = 0
    last_error: str = ""
    delivered_at: str = ""


def compute_signals(store: Store, window: str) -> list[Signal]:
    """Compute the per-plan signals for one scheduled window.

    Signals (all derived from aggregates already in the store):
    - ``open_referral_count``: referrals not yet in a terminal state.
    - ``blocked_task_count``: tasks currently blocked.
    - ``task_completion_ratio``: terminal tasks / all tasks (0.0 if none).
    - ``referral_completion_ratio``: terminal referrals / all referrals.
    - ``coordination_risk_score``: open referrals + 2 * blocked tasks,
      a simple triage score a downstream model can threshold on.
    """
    signals: list[Signal] = []
    for plan in store.plans.values():
        referrals = [r for r in store.referrals.values() if r.plan_id == plan.id]
        tasks = [t for t in store.tasks.values() if t.plan_id == plan.id]
        open_refs = sum(1 for r in referrals if r.status not in TERMINAL_REFERRAL)
        blocked = sum(1 for t in tasks if t.status is TaskStatus.BLOCKED)
        done_tasks = sum(1 for t in tasks if t.status in TERMINAL_TASK)
        done_refs = sum(1 for r in referrals if r.status in TERMINAL_REFERRAL)
        values = {
            "open_referral_count": float(open_refs),
            "blocked_task_count": float(blocked),
            "task_completion_ratio": (done_tasks / len(tasks)) if tasks else 0.0,
            "referral_completion_ratio": (done_refs / len(referrals)) if referrals else 0.0,
            "coordination_risk_score": float(open_refs + 2 * blocked),
        }
        for name, value in values.items():
            signals.append(Signal(name=name, plan_id=plan.id,
                                  patient_ref=plan.patient_ref, value=value,
                                  window=window))
    return signals


class SignalDeliveryPipeline:
    """Computes signals for a window and delivers them with retry + logging.

    ``sink`` is any callable taking a :class:`Signal`; raising means the
    delivery failed and should be retried. ``target`` names the sink in
    the delivery log (e.g. ``"feature-store"``).
    """

    def __init__(self, store: Store, sink: Callable[[Signal], None],
                 target: str = "default", sleep: Callable[[float], None] = time.sleep):
        self.store = store
        self.sink = sink
        self.target = target
        self.sleep = sleep
        self.delivery_log: list[DeliveryRecord] = []
        self._delivered_keys: set[str] = set()

    def deliver_one(self, signal: Signal) -> DeliveryRecord:
        """Deliver one signal with bounded retries; always logs the outcome."""
        record = DeliveryRecord(signal_id=signal.id, delivery_key=signal.delivery_key,
                                target=self.target)
        self.delivery_log.append(record)
        if signal.delivery_key in self._delivered_keys:
            record.status = "duplicate"
            return record
        while record.attempts < MAX_DELIVERY_ATTEMPTS:
            record.attempts += 1
            try:
                self.sink(signal)
            except Exception as exc:  # sink failure: retry, then log as failed
                record.last_error = str(exc)
                if record.attempts >= MAX_DELIVERY_ATTEMPTS:
                    record.status = "failed"
                    return record
                self.sleep(backoff_seconds(record.attempts))
                continue
            self._delivered_keys.add(signal.delivery_key)
            record.status = "delivered"
            record.delivered_at = now_iso()
            return record
        return record

    def run_once(self, window: str) -> dict:
        """One scheduled tick: compute this window's signals and deliver them.

        Returns outcome counts keyed by delivery status.
        """
        counts = {"delivered": 0, "duplicate": 0, "failed": 0}
        for signal in compute_signals(self.store, window):
            record = self.deliver_one(signal)
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    def failed_deliveries(self) -> list[DeliveryRecord]:
        return [r for r in self.delivery_log if r.status == "failed"]
