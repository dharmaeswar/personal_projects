"""Ingest: validate, dedupe and quarantine tasks from product teams.

Every team pushes tasks in the same raw-dict shape. Ingest is the contract
boundary: a task that fails validation never reaches the feed, and a task
that arrives twice (re-delivery, retries) is stored once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import TASK_KINDS, Task

REQUIRED_FIELDS = ("source", "external_id", "title", "kind", "priority", "created_at")


@dataclass
class QuarantinedTask:
    raw: dict
    reason: str


@dataclass
class IngestResult:
    tasks: list[Task] = field(default_factory=list)
    quarantined: list[QuarantinedTask] = field(default_factory=list)
    duplicates_dropped: int = 0


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def validate_raw(raw: dict) -> str | None:
    """Return an error string, or None when the raw task is valid."""
    if not isinstance(raw, dict):
        return "task is not an object"
    for f in REQUIRED_FIELDS:
        if f not in raw or raw[f] in (None, ""):
            return f"missing required field: {f}"
    if raw["kind"] not in TASK_KINDS:
        return f"unknown kind: {raw['kind']!r}"
    if not isinstance(raw["priority"], int) or not 1 <= raw["priority"] <= 5:
        return f"priority must be an int 1..5, got {raw['priority']!r}"
    if _parse_datetime(raw["created_at"]) is None:
        return f"unparseable created_at: {raw['created_at']!r}"
    rel = raw.get("relevance", 0.5)
    if not isinstance(rel, (int, float)) or not 0.0 <= rel <= 1.0:
        return f"relevance must be 0..1, got {rel!r}"
    if "due_at" in raw and raw["due_at"] is not None and _parse_datetime(raw["due_at"]) is None:
        return f"unparseable due_at: {raw['due_at']!r}"
    return None


def ingest(raw_tasks: list[dict]) -> IngestResult:
    """Validate a batch of raw tasks, dedupe on (source, external_id).

    On a duplicate the newest updated_at wins; ties keep the first seen.
    """
    result = IngestResult()
    by_key: dict[tuple[str, str], Task] = {}
    for raw in raw_tasks:
        err = validate_raw(raw)
        if err is not None:
            result.quarantined.append(QuarantinedTask(raw=raw, reason=err))
            continue
        task = Task(
            source=raw["source"],
            external_id=raw["external_id"],
            title=raw["title"],
            kind=raw["kind"],
            priority=raw["priority"],
            created_at=_parse_datetime(raw["created_at"]),
            due_at=_parse_datetime(raw.get("due_at")) if raw.get("due_at") else None,
            owner=raw.get("owner", ""),
            relevance=float(raw.get("relevance", 0.5)),
            payload=raw.get("payload", {}) or {},
            updated_at=_parse_datetime(raw.get("updated_at")) if raw.get("updated_at") else None,
            stale=bool(raw.get("stale", False)),
        )
        prev = by_key.get(task.key)
        if prev is None:
            by_key[task.key] = task
        else:
            result.duplicates_dropped += 1
            if task.updated_at and prev.updated_at and task.updated_at > prev.updated_at:
                by_key[task.key] = task
    result.tasks = list(by_key.values())
    return result
