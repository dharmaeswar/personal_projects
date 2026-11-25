"""Operational AI tooling: an alert triage agent for the data platform.

Owning a large catalog of production datasets means a steady stream
of alerts — freshness breaches, schema drift, volume anomalies,
upstream failures, cost spikes. The triage agent classifies each
alert from its signal (which monitor fired, how far the metric moved,
what changed recently), proposes the diagnostic steps a human would
run first, and points at the likely owner.

The feedback loop is the part that makes it smarter over time: every
resolved alert is recorded with its root cause and the fix that
worked. The next alert with the same signature gets the learned
diagnosis first, instead of starting from scratch. Nothing here calls
a model — the rules and the memory are explicit, so every suggestion
can be traced to the signal or the past resolution that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

CATEGORY_FRESHNESS = "freshness breach"
CATEGORY_SCHEMA_DRIFT = "schema drift"
CATEGORY_VOLUME = "volume anomaly"
CATEGORY_UPSTREAM = "upstream failure"
CATEGORY_COST = "cost spike"
CATEGORY_UNKNOWN = "unknown"


@dataclass
class Alert:
    alert_id: str
    source: str  # monitor or system that raised it, e.g. "freshness-monitor"
    message: str
    metric: str  # e.g. "latest_event_age_minutes", "row_count", "schema_hash"
    observed: float
    threshold: float
    timestamp: pd.Timestamp
    dataset: str = ""


@dataclass
class TriageResult:
    alert_id: str
    category: str
    severity: str  # "p2" or "p3"
    likely_cause: str
    suggested_steps: list[str]
    learned: bool = False  # True when a past resolution supplied the diagnosis

    def __str__(self) -> str:  # pragma: no cover - convenience only
        learned = " (learned from a past resolution)" if self.learned else ""
        steps = "\n".join(f"  - {step}" for step in self.suggested_steps)
        return (
            f"[{self.severity.upper()}] {self.alert_id}: {self.category}{learned}\n"
            f"Likely cause: {self.likely_cause}\n{steps}"
        )


def _signature(alert: Alert) -> str:
    """Stable key for the feedback loop: source + metric + dataset."""
    return f"{alert.source}|{alert.metric}|{alert.dataset}"


@dataclass
class TriageMemory:
    """Past resolutions, keyed by alert signature."""

    resolutions: dict[str, dict[str, str]] = field(default_factory=dict)

    def record_resolution(
        self, alert: Alert, root_cause: str, action: str
    ) -> None:
        self.resolutions[_signature(alert)] = {
            "root_cause": root_cause,
            "action": action,
        }

    def lookup(self, alert: Alert) -> dict[str, str] | None:
        return self.resolutions.get(_signature(alert))


def classify_alert(
    alert: Alert, memory: TriageMemory | None = None
) -> TriageResult:
    """Classify an alert and propose diagnostics.

    A recorded resolution for the same signature wins: the agent
    repeats what worked last time before falling back to the rules.
    Severity is P2 when the observed value is at least twice the
    threshold (or the source is an upstream failure); otherwise P3.
    """
    if memory is not None:
        learned = memory.lookup(alert)
        if learned is not None:
            return TriageResult(
                alert_id=alert.alert_id,
                category=_category_for(alert),
                severity=_severity_for(alert),
                likely_cause=learned["root_cause"],
                suggested_steps=[
                    f"Apply the fix that worked last time: {learned['action']}",
                    "Confirm the metric returns inside its threshold before closing.",
                ],
                learned=True,
            )
    category = _category_for(alert)
    return TriageResult(
        alert_id=alert.alert_id,
        category=category,
        severity=_severity_for(alert),
        likely_cause=_likely_cause(alert, category),
        suggested_steps=_steps_for(alert, category),
    )


def _category_for(alert: Alert) -> str:
    source = alert.source.lower()
    metric = alert.metric.lower()
    message = alert.message.lower()
    if "schema" in source or "schema" in metric or "drift" in message:
        return CATEGORY_SCHEMA_DRIFT
    if "freshness" in source or "age" in metric or "stale" in message:
        return CATEGORY_FRESHNESS
    if "volume" in source or "row_count" in metric or "count" in metric:
        return CATEGORY_VOLUME
    if "upstream" in source or "upstream" in message or "source" in metric:
        return CATEGORY_UPSTREAM
    if "cost" in source or "cost" in metric or "spend" in metric:
        return CATEGORY_COST
    return CATEGORY_UNKNOWN


def _severity_for(alert: Alert) -> str:
    if alert.threshold and alert.observed >= 2 * alert.threshold:
        return "p2"
    if "upstream" in alert.source.lower():
        return "p2"
    return "p3"


def _likely_cause(alert: Alert, category: str) -> str:
    if category == CATEGORY_FRESHNESS:
        return "upstream extraction stalled or the pipeline run failed before writing"
    if category == CATEGORY_SCHEMA_DRIFT:
        return "source system shipped a schema change the contract did not expect"
    if category == CATEGORY_VOLUME:
        return "source volume shifted (holiday, outage, or a backfill landing at once)"
    if category == CATEGORY_UPSTREAM:
        return "a source system or its connector is down or throttling"
    if category == CATEGORY_COST:
        return "a runaway query or an uncompacted table is scanning far more data than usual"
    return "no signal matches a known category — inspect the alert payload directly"


def _steps_for(alert: Alert, category: str) -> list[str]:
    common = [
        f"Check the latest run for dataset '{alert.dataset or 'unknown'}' in the orchestrator.",
        "Confirm whether the same alert fired for sibling datasets (shared cause) or only this one.",
    ]
    specific = {
        CATEGORY_FRESHNESS: [
            "Check the extractor watermark and the last successful write time.",
            "Look for a failed or stuck task in the DAG run history.",
        ],
        CATEGORY_SCHEMA_DRIFT: [
            "Diff the observed schema against the data contract for this dataset.",
            "If a column was added, check whether the contract needs a versioned update.",
        ],
        CATEGORY_VOLUME: [
            "Compare today's row count with the same weekday over the last four weeks.",
            "Check whether a backfill window landed in this period.",
        ],
        CATEGORY_UPSTREAM: [
            "Check the source system's status and the connector's error log.",
            "Verify the checkpoint/offset — a consumer may be stuck behind a poison record.",
        ],
        CATEGORY_COST: [
            "Find the top queries by bytes scanned in the last 24 hours.",
            "Check whether the table needs compaction (many small files).",
        ],
        CATEGORY_UNKNOWN: [
            "Read the full alert payload and route it to the dataset owner.",
        ],
    }
    return specific.get(category, specific[CATEGORY_UNKNOWN]) + common
