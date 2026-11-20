"""Tests for the Operational AI module (customer detections, scoring,
agentic workflow, latency/cost tracking). All data is synthetic."""

from datetime import datetime

from cold_chain.models import TelemetryReading
from cold_chain.operational_ai import (
    AgentWorkflow,
    DetectionRule,
    LabeledEvent,
    cost_summary,
    detect,
    run_demo,
    score_detections,
)


def _reading(reading_id="R1", temp=-15.0, humidity=50.0):
    return TelemetryReading(
        reading_id=reading_id, shipment_id="S1", device_id="D1",
        recorded_at=datetime(2026, 11, 14, 8, 0, 0),
        temperature_c=temp, humidity_pct=humidity,
    )


def _rule():
    return DetectionRule("TEMP_HIGH", "Warm shipment", "temperature_c",
                         ">", 8.0, severity="critical",
                         action="Inspect the door seal")


def test_rule_operators():
    reading = _reading(temp=9.0)
    assert DetectionRule("A", "x", "temperature_c", ">", 8.0).matches(reading)
    assert not DetectionRule("A", "x", "temperature_c", "<", 8.0).matches(reading)
    assert DetectionRule("A", "x", "temperature_c", ">=", 9.0).matches(reading)
    assert DetectionRule("A", "x", "temperature_c", "<=", 9.0).matches(reading)
    assert DetectionRule("A", "x", "temperature_c", "==", 9.0).matches(reading)
    assert not DetectionRule("A", "x", "temperature_c", "==", 9.5).matches(reading)


def test_rule_ignores_missing_field_value():
    reading = _reading(humidity=None)
    rule = DetectionRule("H", "humid", "humidity_pct", ">", 80.0)
    assert not rule.matches(reading)


def test_detect_returns_one_detection_per_hit():
    readings = [_reading("R1", temp=9.0), _reading("R2", temp=-15.0)]
    detections = detect(readings, [_rule()])
    assert len(detections) == 1
    assert detections[0].reading_id == "R1"
    assert detections[0].severity == "critical"
    assert detections[0].recommended_action == "Inspect the door seal"
    assert detections[0].latency_ms == 1.5
    assert detections[0].compute_cost_usd > 0


def test_detect_empty_inputs():
    assert detect([], [_rule()]) == []
    assert detect([_reading()], []) == []


def test_score_precision_recall_f1():
    detections = detect([_reading("R1", temp=9.0), _reading("R2", temp=9.5)],
                        [_rule()])
    labels = [LabeledEvent("R1", True), LabeledEvent("R2", False),
              LabeledEvent("R3", True)]
    score = score_detections(detections, labels)
    assert (score.true_positives, score.false_positives,
            score.false_negatives) == (1, 1, 1)
    assert score.precision() == 0.5
    assert score.recall() == 0.5
    assert score.f1() == 0.5


def test_score_empty_is_zero_not_crash():
    score = score_detections([], [])
    assert score.precision() == 0.0
    assert score.recall() == 0.0
    assert score.f1() == 0.0


def test_workflow_recommend_and_resolve():
    detection = detect([_reading("R1", temp=9.0)], [_rule()])[0]
    workflow = AgentWorkflow()
    rec = workflow.recommend(detection)
    assert rec["recommended_action"] == "Inspect the door seal"
    assert rec["status"] == "open"
    workflow.record_outcome(detection, "Door seal replaced", resolved=True)
    assert detection.status == "resolved"
    assert workflow.summary() == {"outcomes_recorded": 1, "resolved": 1,
                                  "resolution_rate": 1.0}


def test_workflow_unresolved_stays_actioned():
    detection = detect([_reading("R1", temp=9.0)], [_rule()])[0]
    workflow = AgentWorkflow()
    workflow.record_outcome(detection, "Escalated to carrier", resolved=False)
    assert detection.status == "actioned"
    assert workflow.summary()["resolution_rate"] == 0.0


def test_cost_summary_scales_with_detections():
    detections = detect([_reading("R1", temp=9.0), _reading("R2", temp=9.5)],
                        [_rule()])
    summary = cost_summary(detections)
    assert summary["detections"] == 2
    assert summary["total_latency_ms"] == 3.0
    assert summary["avg_latency_ms"] == 1.5
    assert summary["total_cost_usd"] > 0
    assert cost_summary([])["total_cost_usd"] == 0


def test_demo_is_deterministic_and_scores():
    first, second = run_demo(), run_demo()
    assert first == second
    assert first["readings"] == 48
    assert first["detections"] == 15
    assert first["true_positives"] == 12
    assert first["false_positives"] == 3
    assert first["false_negatives"] == 0
    assert first["precision"] == 0.8
    assert first["recall"] == 1.0
    assert first["f1"] == 0.8889
    assert 0.0 < first["resolution_rate"] <= 1.0
    assert first["total_cost_usd"] > 0
