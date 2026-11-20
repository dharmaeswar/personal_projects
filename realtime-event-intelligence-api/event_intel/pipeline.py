"""Consumer pipeline: drain the stream, score, dedupe, persist, alert.

Each polled record carries a signal dict with source_id, event_type,
text, reliability, keyword_severity, corroborations and age_seconds.
The pipeline scores it, stores it (dropping duplicates), and counts
how many alerts each run produced.
"""

from __future__ import annotations

from .scoring import band, score_event
from .store import EventStore
from .stream import StreamTopic


def run_consumer(
    topic: StreamTopic,
    store: EventStore,
    group: str,
    max_records: int = 100,
) -> dict:
    """Process one batch for a consumer group; returns run statistics."""
    records = topic.poll(group, max_records=max_records)
    processed = 0
    alerts = 0
    duplicates = 0
    for record in records:
        signal = record.value
        score = score_event(
            reliability=float(signal.get("reliability", 0.5)),
            keyword_severity=float(signal.get("keyword_severity", 0.5)),
            corroborations=int(signal.get("corroborations", 0)),
            age_seconds=float(signal.get("age_seconds", 0.0)),
        )
        result = store.ingest(
            source_id=str(signal["source_id"]),
            event_type=str(signal["event_type"]),
            text=str(signal["text"]),
            score=score,
            band_name=band(score),
        )
        processed += 1
        if result["status"] == "duplicate":
            duplicates += 1
        elif result.get("alert_id") is not None:
            alerts += 1
    topic.commit(group, records)
    return {
        "processed": processed,
        "alerts": alerts,
        "duplicates": duplicates,
        "lag_after": topic.lag(group),
    }
