"""Orchestration: run the member-context streaming pipeline end to end.

Stages, in order: generate synthetic events → produce to the
``member-events`` Kafka-style topic → consume by consumer group →
validate against data contracts (quarantine + DLQ) → dedupe (exactly-once
effect) → sessionize → build point-in-time context snapshots → build the
ML snapshot layer and the LLM context-document layer → record lineage →
evaluate SLOs. A run manifest summarises the run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .broker import ConsumerGroup, InMemoryBroker
from .context_layers import (
    action_journey_catalogue,
    build_llm_documents,
    build_snapshot_rows,
)
from .contracts import CONTRACTS, check_quality
from .events import MemberEvent, generate_events
from .lineage import LineageEntry, evaluate_slo, fingerprint
from .streaming import build_sessions

TOPIC = "member-events"
GROUP_ID = "member-context-builders"


@dataclass
class RunManifest:
    run_id: str
    as_of: str
    produced: int
    consumed: int
    valid: int
    quarantined: int
    duplicates_dropped: int
    sessions: int
    snapshot_rows: int
    llm_documents: int
    lineage: list[dict] = field(default_factory=list)
    slo: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of,
            "produced": self.produced,
            "consumed": self.consumed,
            "valid": self.valid,
            "quarantined": self.quarantined,
            "duplicates_dropped": self.duplicates_dropped,
            "sessions": self.sessions,
            "snapshot_rows": self.snapshot_rows,
            "llm_documents": self.llm_documents,
            "lineage": self.lineage,
            "slo": self.slo,
        }


def run_pipeline(
    n_members: int = 40,
    events_per_member: int = 25,
    seed: int = 42,
    as_of: datetime | None = None,
) -> tuple[RunManifest, dict]:
    """Run the full pipeline and return the manifest plus the layers."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    as_of = as_of or datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)

    # 1. Ingest: synthetic events onto the Kafka-style topic.
    events = generate_events(n_members, events_per_member, seed=seed)
    broker = InMemoryBroker()
    topic = broker.create_topic(TOPIC, partitions=6)
    for event in events:
        topic.produce(event)

    # 2. Consume: one consumer group reads every partition in offset order.
    group = ConsumerGroup(GROUP_ID)
    consumed: list[MemberEvent] = []
    for partition in range(topic.partitions):
        offset = group.committed_offset(TOPIC, partition)
        records = topic.fetch(partition, offset, max_records=100000)
        consumed.extend(r.event for r in records)
        if records:
            group.commit(TOPIC, partition, records[-1].offset + 1)
    assert group.total_lag(topic) == 0, "consumer group must drain the topic"

    # 3. Data quality: contracts, quarantine, exactly-once dedupe.
    quality = check_quality(consumed, now=as_of + timedelta(days=1))
    valid = quality.valid

    # 4. Stream processing: sessions + point-in-time context.
    sessions = build_sessions(valid)
    member_ids = sorted({e.member_id for e in valid})
    snapshots = build_snapshot_rows(valid, member_ids, as_of)
    documents = build_llm_documents(valid, member_ids, as_of)
    catalogue = action_journey_catalogue()

    # 5. Lineage: one entry per layer, fingerprinted.
    lineage = [
        LineageEntry(
            run_id=run_id,
            layer="member_context_snapshot",
            source_topic=TOPIC,
            contract_version="1.0",
            input_rows=len(valid),
            output_rows=len(snapshots),
            fingerprint=fingerprint([r.to_dict() for r in snapshots]),
        ).to_dict(),
        LineageEntry(
            run_id=run_id,
            layer="llm_context_document",
            source_topic=TOPIC,
            contract_version="1.0",
            input_rows=len(valid),
            output_rows=len(documents),
            fingerprint=fingerprint([d.to_dict() for d in documents]),
        ).to_dict(),
        LineageEntry(
            run_id=run_id,
            layer="action_journey_catalogue",
            source_topic=TOPIC,
            contract_version="1.0",
            input_rows=len(catalogue),
            output_rows=len(catalogue),
            fingerprint=fingerprint(catalogue),
        ).to_dict(),
    ]

    # 6. SLOs: p95 freshness from ingest lag, completeness from valid share.
    lags = sorted(
        (e.ingested_at - e.occurred_at).total_seconds() / 60.0 for e in valid
    )
    p95_lag = lags[int(0.95 * (len(lags) - 1))] if lags else 0.0
    slo = evaluate_slo(
        run_id,
        valid_rows=len(valid),
        quarantined_rows=len(quality.quarantined),
        freshness_p95_minutes=p95_lag,
    ).to_dict()

    manifest = RunManifest(
        run_id=run_id,
        as_of=as_of.isoformat(),
        produced=topic.total_records(),
        consumed=len(consumed),
        valid=len(valid),
        quarantined=len(quality.quarantined),
        duplicates_dropped=quality.duplicates_dropped,
        sessions=len(sessions),
        snapshot_rows=len(snapshots),
        llm_documents=len(documents),
        lineage=lineage,
        slo=slo,
    )
    layers = {
        "sessions": [s.__dict__ for s in sessions],
        "snapshots": [r.to_dict() for r in snapshots],
        "llm_documents": [d.to_dict() for d in documents],
        "catalogue": catalogue,
        "quarantined": [
            {
                "event_id": q.event_id,
                "member_id": q.member_id,
                "event_type": q.event_type,
                "reason": q.reason,
            }
            for q in quality.quarantined
        ],
    }
    return manifest, layers


def manifest_json(manifest: RunManifest) -> str:
    return json.dumps(manifest.to_dict(), indent=2, default=str)
