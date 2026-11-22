"""Consumer pipeline: drain the stream, score, dedupe, persist, alert.

Each polled record carries a signal dict with source_id, event_type,
text, reliability, keyword_severity, corroborations and age_seconds.
The pipeline validates it (malformed records go to the dead-letter
queue), skips records already processed (exactly-once on redelivery),
scores it, stores it (dropping duplicates), buckets it into a
tumbling window, and counts how many alerts each run produced.
"""

from __future__ import annotations

from .checkpoint import CheckpointStore, DeadLetterQueue, validate_signal
from .scoring import band, score_event
from .store import EventStore
from .stream import StreamTopic
from .windowing import TumblingWindows


def run_consumer(
    topic: StreamTopic,
    store: EventStore,
    group: str,
    max_records: int = 100,
    checkpoint: CheckpointStore | None = None,
    dead_letter: DeadLetterQueue | None = None,
    windows: TumblingWindows | None = None,
) -> dict:
    """Process one batch for a consumer group; returns run statistics."""
    if checkpoint is None:
        checkpoint = CheckpointStore()
    if dead_letter is None:
        dead_letter = DeadLetterQueue()
    records = topic.poll(group, max_records=max_records)
    processed = 0
    alerts = 0
    duplicates = 0
    invalid = 0
    redelivered = 0
    for record in records:
        if checkpoint.already_processed(record.partition, record.offset):
            redelivered += 1
            continue
        signal = record.value
        problems = validate_signal(signal)
        if problems:
            dead_letter.add(record.partition, record.offset, signal, problems)
            invalid += 1
            checkpoint.mark_processed(record.partition, record.offset)
            continue
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
        checkpoint.mark_processed(record.partition, record.offset)
        if windows is not None:
            event_time = float(signal.get("event_time", 0.0))
            windows.add(event_time, band(score))
        if result["status"] == "duplicate":
            duplicates += 1
        elif result.get("alert_id") is not None:
            alerts += 1
    topic.commit(group, records)
    return {
        "processed": processed,
        "alerts": alerts,
        "duplicates": duplicates,
        "invalid": invalid,
        "redelivered_skipped": redelivered,
        "dead_letter": len(dead_letter),
        "lag_after": topic.lag(group),
    }
