"""Actions: the standard task actions and detail views.

Every task supports the same action vocabulary. Transitions are a small
state machine: open tasks can be actioned, dismissed or snoozed; snoozed
tasks reopen when their snooze expires; terminal states reject new actions.
Idempotency keys make retries safe: replaying an action with the same key
returns the original result instead of acting twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import STANDARD_ACTIONS, DetailView, Task

# (current state, action) -> new state. Actions not listed are invalid.
TRANSITIONS: dict[tuple[str, str], str] = {
    ("open", "approve"): "actioned",
    ("open", "reject"): "actioned",
    ("open", "complete"): "actioned",
    ("open", "dismiss"): "dismissed",
    ("open", "snooze"): "snoozed",
    ("snoozed", "dismiss"): "dismissed",
    ("snoozed", "approve"): "actioned",
    ("snoozed", "reject"): "actioned",
    ("snoozed", "complete"): "actioned",
    ("snoozed", "snooze"): "snoozed",
}

# Which detail-view fields each kind shows, in order. Values come from the
# task payload; missing values render as "—".
DETAIL_FIELDS = {
    "approval": ("requester", "amount", "vendor", "policy_checks"),
    "receipt": ("merchant", "amount", "matched_expense", "receipt_date"),
    "setup": ("step", "progress", "blocked_by"),
    "recommendation": ("savings", "basis"),
    "alert": ("severity", "source_detail"),
}


class ActionError(ValueError):
    pass


class ActionLog:
    """Records applied actions; replays by idempotency key return the stored result."""

    def __init__(self) -> None:
        self._by_key: dict[str, dict] = {}

    def apply(
        self,
        task: Task,
        action: str,
        *,
        idempotency_key: str,
        now: datetime,
        snooze_days: int = 1,
    ) -> dict:
        if idempotency_key in self._by_key:
            return dict(self._by_key[idempotency_key], replayed=True)
        if action not in STANDARD_ACTIONS:
            raise ActionError(f"unknown action: {action!r}")
        if action == "open_detail":
            result = {"task": task.key, "action": action, "state": task.state, "replayed": False}
            self._by_key[idempotency_key] = result
            return result
        if action not in task.allowed_actions():
            raise ActionError(f"action {action!r} not valid for kind {task.kind!r}")
        new_state = TRANSITIONS.get((task.state, action))
        if new_state is None:
            raise ActionError(f"cannot {action!r} a {task.state} task")
        task.state = new_state
        task.snoozed_until = now + timedelta(days=snooze_days) if action == "snooze" else None
        result = {"task": task.key, "action": action, "state": new_state, "replayed": False}
        self._by_key[idempotency_key] = result
        return result

    def wake_snoozed(self, tasks: list[Task], now: datetime) -> int:
        """Reopen snoozed tasks whose snooze has expired. Returns count woken."""
        woken = 0
        for t in tasks:
            if t.state == "snoozed" and t.snoozed_until and t.snoozed_until <= now:
                t.state = "open"
                t.snoozed_until = None
                woken += 1
        return woken


def detail_view(task: Task) -> DetailView:
    fields = []
    for name in DETAIL_FIELDS[task.kind]:
        value = task.payload.get(name, "—")
        fields.append((name.replace("_", " ").title(), str(value)))
    fields.append(("Priority", str(task.priority)))
    fields.append(("Due", task.due_at.isoformat() if task.due_at else "—"))
    return DetailView(
        task_key=task.key,
        title=task.title,
        fields=fields,
        actions=task.allowed_actions(),
        source=task.source,
    )
