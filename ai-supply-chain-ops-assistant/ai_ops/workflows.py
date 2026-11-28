"""Workflow automation with human review.

The assistant drafts follow-up tasks from analytics signals (reorder,
expedite, transfer), but a task only becomes real work when a human
approves it. Approvals and rejections go into an audit log, and repeating
a request with the same idempotency key returns the original task instead
of creating a duplicate — the reliable error handling the real product
needs when it calls enterprise APIs.
"""

import itertools

from .analytics import INVENTORY, days_of_cover, reorder_point

_counter = itertools.count(1)


class WorkflowStore:
    """In-memory store for drafted workflow tasks and their audit log."""

    def __init__(self):
        self.tasks = {}
        self.by_key = {}
        self.audit = []

    def draft_task(self, kind, sku, warehouse, detail, idempotency_key):
        """Draft a task. Repeating the same key returns the original task."""
        if idempotency_key in self.by_key:
            return self.by_key[idempotency_key], False
        task_id = f"TASK-{next(_counter):04d}"
        task = {
            "id": task_id,
            "kind": kind,
            "sku": sku,
            "warehouse": warehouse,
            "detail": detail,
            "status": "draft",
            "idempotency_key": idempotency_key,
        }
        self.tasks[task_id] = task
        self.by_key[idempotency_key] = task
        self.audit.append({"task_id": task_id, "action": "drafted", "by": "assistant"})
        return task, True

    def review(self, task_id, approve, reviewer):
        """Approve or reject a drafted task. Only drafts can be reviewed."""
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown task {task_id}")
        if task["status"] != "draft":
            raise ValueError(f"task {task_id} is already {task['status']}")
        task["status"] = "approved" if approve else "rejected"
        self.audit.append({
            "task_id": task_id,
            "action": task["status"],
            "by": reviewer,
        })
        return task

    def list_tasks(self, status=None):
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return tasks


def draft_reorders(store):
    """Draft a reorder task for every low-cover row below its reorder point.

    Returns (tasks, created_count). Tasks are drafts only — nothing is
    ordered until a human approves.
    """
    drafted = []
    created = 0
    for row in INVENTORY:
        point = reorder_point(row)
        if row["on_hand"] < point:
            qty = max(0, round(point * 2 - row["on_hand"]))
            task, is_new = store.draft_task(
                kind="reorder",
                sku=row["sku"],
                warehouse=row["warehouse"],
                detail=(
                    f"On-hand {row['on_hand']} is below reorder point {point} "
                    f"({days_of_cover(row)} days of cover). Suggested order: {qty} units."
                ),
                idempotency_key=f"reorder-{row['sku']}-{row['warehouse']}",
            )
            drafted.append(task)
            created += 1 if is_new else 0
    return drafted, created


def draft_transfer(store, sku, from_warehouse, to_warehouse, units):
    """Draft a transfer task, enforcing the runbook guardrails.

    Refuses to draft a transfer that would take the last unit out of a
    center, or move stock to a center that already has 30+ days of cover.
    """
    source = next(
        (r for r in INVENTORY if r["sku"] == sku and r["warehouse"] == from_warehouse),
        None,
    )
    dest = next(
        (r for r in INVENTORY if r["sku"] == sku and r["warehouse"] == to_warehouse),
        None,
    )
    if source is None or dest is None:
        raise ValueError(f"no inventory row for {sku} at one of the warehouses")
    if units >= source["on_hand"]:
        raise ValueError("refused: transfer would take the last units out of the sending center")
    if days_of_cover(dest) >= 30:
        raise ValueError("refused: destination already has 30+ days of cover")
    task, _ = store.draft_task(
        kind="transfer",
        sku=sku,
        warehouse=to_warehouse,
        detail=f"Move {units} units of {sku} from {from_warehouse} to {to_warehouse}.",
        idempotency_key=f"transfer-{sku}-{from_warehouse}-{to_warehouse}-{units}",
    )
    return task
