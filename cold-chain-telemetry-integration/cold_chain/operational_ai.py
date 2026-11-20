"""Operational AI: customer-defined detections and agentic workflows.

Sits on top of the normalised telemetry this project already loads. A
customer defines detection rules (for example, "temperature above 8 C for a
frozen shipment means a door left open"), the engine turns matching
readings into detections, scores detection quality against labelled events,
and drives a small agentic workflow: detection -> recommended action ->
recorded outcome. Latency and compute cost are tracked per detection so
reliability, response time and cost stay visible as usage grows.

All data here is synthetic and seeded; nothing describes a real shipment,
customer, or detection. Computer-vision and edge-device behaviour are out
of scope for this module: it works on the telemetry stream the pipeline
already normalises.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import Shipment, TelemetryReading

# Cost model for the demo: each detection costs a fixed amount of
# evaluation compute plus a per-millisecond charge, so cost scales with
# the number of detections and the time spent scoring them.
COST_PER_DETECTION_USD = 0.002
COST_PER_MS_USD = 0.00001


@dataclass(frozen=True)
class DetectionRule:
    """One customer-defined detection rule.

    field: which reading attribute to test ("temperature_c" or
    "humidity_pct"). operator: one of ">", "<", ">=", "<=", "==".
    action: the recommended action shown to the operator when the rule
    fires, for example "Inspect the trailer door seal".
    """

    rule_id: str
    name: str
    field: str
    operator: str
    threshold: float
    severity: str = "warning"
    action: str = "Review the shipment"

    def matches(self, reading: TelemetryReading) -> bool:
        value = getattr(reading, self.field, None)
        if value is None:
            return False
        if self.operator == ">":
            return value > self.threshold
        if self.operator == "<":
            return value < self.threshold
        if self.operator == ">=":
            return value >= self.threshold
        if self.operator == "<=":
            return value <= self.threshold
        if self.operator == "==":
            return value == self.threshold
        raise ValueError(f"unknown operator: {self.operator}")


@dataclass
class Detection:
    rule_id: str
    reading_id: str
    shipment_id: str
    recorded_at: datetime
    value: float
    severity: str
    recommended_action: str
    status: str = "open"
    latency_ms: float = 0.0
    compute_cost_usd: float = 0.0


@dataclass(frozen=True)
class LabeledEvent:
    """A human-labelled ground-truth event for scoring.

    reading_id links the label to the reading it describes; is_real is
    True when the event really happened (a true positive target).
    """

    reading_id: str
    is_real: bool


@dataclass
class QualityScore:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return (self.true_positives / denom) if denom else 0.0

    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return (self.true_positives / denom) if denom else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return (2 * p * r / (p + r)) if (p + r) else 0.0


def detect(readings: list[TelemetryReading],
           rules: list[DetectionRule],
           latency_ms_per_reading: float = 1.5) -> list[Detection]:
    """Run every rule over every reading; return one Detection per hit.

    Latency is charged per reading evaluated, cost per detection raised,
    so both totals grow honestly with volume.
    """
    detections: list[Detection] = []
    for reading in readings:
        for rule in rules:
            if rule.matches(reading):
                cost = COST_PER_DETECTION_USD + latency_ms_per_reading * COST_PER_MS_USD
                detections.append(Detection(
                    rule_id=rule.rule_id,
                    reading_id=reading.reading_id,
                    shipment_id=reading.shipment_id,
                    recorded_at=reading.recorded_at,
                    value=getattr(reading, rule.field),
                    severity=rule.severity,
                    recommended_action=rule.action,
                    latency_ms=latency_ms_per_reading,
                    compute_cost_usd=round(cost, 6),
                ))
    return detections


def score_detections(detections: list[Detection],
                     labels: list[LabeledEvent]) -> QualityScore:
    """Score detections against labelled ground truth by reading_id."""
    real_ids = {label.reading_id for label in labels if label.is_real}
    detected_ids = {d.reading_id for d in detections}
    return QualityScore(
        true_positives=len(real_ids & detected_ids),
        false_positives=len(detected_ids - real_ids),
        false_negatives=len(real_ids - detected_ids),
    )


@dataclass
class WorkflowOutcome:
    detection_key: str
    action_taken: str
    resolved: bool


class AgentWorkflow:
    """Detection -> recommended action -> recorded outcome.

    The agent never changes a detection on its own: it proposes the
    rule's recommended action, and a human (or a calling system) records
    what was actually done and whether the issue resolved. The summary
    is the detection-quality feedback loop for the next rule revision.
    """

    def __init__(self) -> None:
        self.outcomes: list[WorkflowOutcome] = []

    def recommend(self, detection: Detection) -> dict:
        return {
            "detection": f"{detection.rule_id}:{detection.reading_id}",
            "shipment_id": detection.shipment_id,
            "severity": detection.severity,
            "recommended_action": detection.recommended_action,
            "status": detection.status,
        }

    def record_outcome(self, detection: Detection, action_taken: str,
                       resolved: bool) -> WorkflowOutcome:
        outcome = WorkflowOutcome(
            detection_key=f"{detection.rule_id}:{detection.reading_id}",
            action_taken=action_taken,
            resolved=resolved,
        )
        self.outcomes.append(outcome)
        detection.status = "resolved" if resolved else "actioned"
        return outcome

    def summary(self) -> dict:
        total = len(self.outcomes)
        resolved = sum(1 for o in self.outcomes if o.resolved)
        return {
            "outcomes_recorded": total,
            "resolved": resolved,
            "resolution_rate": (resolved / total) if total else 0.0,
        }


def cost_summary(detections: list[Detection]) -> dict:
    """Total latency and compute cost for a batch of detections."""
    total_ms = sum(d.latency_ms for d in detections)
    total_cost = round(sum(d.compute_cost_usd for d in detections), 4)
    return {
        "detections": len(detections),
        "total_latency_ms": round(total_ms, 1),
        "avg_latency_ms": round(total_ms / len(detections), 2) if detections else 0.0,
        "total_cost_usd": total_cost,
    }


def run_demo(seed: int = 7) -> dict:
    """Seeded end-to-end demo: 6 shipments, 48 readings, 2 rules.

    12 readings are real excursions (labelled true); the warm rule also
    fires on 3 borderline readings that are labelled false. Returns the
    counts so tests and the README can quote them.
    """
    rng = random.Random(seed)
    base = datetime(2026, 11, 14, 8, 0, 0)
    shipments = [
        Shipment(f"S{i}", f"O{i}", "Acme Foods", "Buffalo, NY",
                 "Chicago, IL", "frozen meals", -20.0, -10.0,
                 "2026-11-14", "NorthStar Carrier")
        for i in range(6)
    ]
    readings: list[TelemetryReading] = []
    labels: list[LabeledEvent] = []
    for n in range(48):
        ship = shipments[n % 6]
        excursion = n in {3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47}
        borderline = n in {5, 17, 29}
        temp = rng.uniform(8.5, 14.0) if excursion else (
            rng.uniform(8.1, 8.4) if borderline else rng.uniform(-19.0, -11.0))
        reading = TelemetryReading(
            reading_id=f"R{n:03d}", shipment_id=ship.shipment_id,
            device_id=f"D{n % 6}", recorded_at=base + timedelta(minutes=15 * n),
            temperature_c=round(temp, 1),
            humidity_pct=round(rng.uniform(40.0, 60.0), 1),
        )
        readings.append(reading)
        labels.append(LabeledEvent(reading.reading_id, excursion))
    rules = [
        DetectionRule("TEMP_HIGH", "Warm shipment", "temperature_c", ">", 8.0,
                      severity="critical",
                      action="Inspect the trailer door seal and check the reefer unit"),
        DetectionRule("TEMP_LOW", "Too cold", "temperature_c", "<", -22.0,
                      severity="warning",
                      action="Check the reefer set point for over-cooling"),
    ]
    detections = detect(readings, rules)
    score = score_detections(detections, labels)
    workflow = AgentWorkflow()
    for detection in detections:
        workflow.recommend(detection)
        # Demo outcome rule: severe excursions (value over 10 C) are
        # confirmed and fixed on the spot; milder ones stay actioned.
        workflow.record_outcome(detection, detection.recommended_action,
                                resolved=detection.value > 10.0)
    return {
        "readings": len(readings),
        "detections": len(detections),
        "precision": round(score.precision(), 4),
        "recall": round(score.recall(), 4),
        "f1": round(score.f1(), 4),
        "true_positives": score.true_positives,
        "false_positives": score.false_positives,
        "false_negatives": score.false_negatives,
        "resolution_rate": round(workflow.summary()["resolution_rate"], 4),
        **cost_summary(detections),
    }


if __name__ == "__main__":
    for key, value in run_demo().items():
        print(f"{key}: {value}")
