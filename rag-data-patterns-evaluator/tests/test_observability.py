import json

from rag_evaluator.observability import Telemetry


def test_span_records_duration_and_status():
    tel = Telemetry()
    span = tel.start_span("ingest.chunk", {"strategy": "sentence"})
    tel.end_span(span, status="ok")
    assert len(tel.spans) == 1
    assert tel.spans[0]["status"] == "ok"
    assert tel.spans[0]["duration_ms"] >= 0
    assert tel.spans[0]["attributes"]["strategy"] == "sentence"


def test_events_and_counters():
    tel = Telemetry()
    tel.record_event("ingest.document_rejected", {"id": "bad-doc"})
    tel.increment("docs_ingested", 2)
    tel.increment("docs_ingested", 3)
    assert tel.events[0]["name"] == "ingest.document_rejected"
    assert tel.counters["docs_ingested"] == 5


def test_span_summary_groups_by_name():
    tel = Telemetry()
    for _ in range(2):
        tel.end_span(tel.start_span("api.retrieve"))
    tel.end_span(tel.start_span("ingest.chunk"))
    summary = tel.span_summary()
    assert summary["api.retrieve"]["count"] == 2
    assert summary["ingest.chunk"]["count"] == 1
    assert summary["api.retrieve"]["total_duration_ms"] >= 0


def test_to_jsonl_is_valid_json_lines():
    tel = Telemetry()
    tel.end_span(tel.start_span("ingest.chunk"))
    tel.record_event("ingest.done", {})
    lines = tel.to_jsonl().strip().split("\n")
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert {record["type"] for record in records} == {"span", "event"}
