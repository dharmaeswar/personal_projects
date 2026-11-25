"""Run the Data Forge extension end to end and write the report.

Usage: python run_data_forge.py [--out DIR]
Simulates one day of lake work: extract property-listing events from
a Postgres replica, a Kafka shard, and a Lambda ingest batch; check
the curated table against its data contract; commit an Iceberg-style
snapshot; plan compaction; and triage one planted freshness alert.
Writes data_forge_report.txt in the project root.

All data is synthetic and seeded. No live source system is involved.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lakehouse.compaction import (
    TableFile,
    expire_snapshots,
    partition_value,
    plan_compaction,
)
from lakehouse.contracts import DataContract, validate_contract
from lakehouse.extract import (
    ShardCheckpoint,
    consume_shard,
    detect_schema_drift,
    extract_from_replica,
    ingest_lambda_events,
    plan_backfill,
)
from lakehouse.snapshots import commit_snapshot, list_snapshots
from lakehouse.triage import Alert, TriageMemory, classify_alert


def _seeded_events(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2026-11-25 08:00", tz="UTC")
    return pd.DataFrame(
        {
            "event_id": [f"evt-{i:04d}" for i in range(n)],
            "listing_id": rng.integers(1000, 9999, size=n),
            "event_type": rng.choice(
                ["view", "save", "tour_booked", "price_change"], size=n
            ),
            "price": rng.integers(150_000, 1_200_000, size=n).astype(float),
            "updated_at": [
                base + pd.Timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)
            ],
            "event_time": [
                base + pd.Timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)
            ],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="lakehouse_tables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    lines: list[str] = ["# Data Forge run — 2026-11-25", ""]
    events = _seeded_events()

    # 1. Extract from the Postgres replica (watermarked, capped batches).
    replica = extract_from_replica(events, watermark=None, batch_size=100)
    lines.append(
        f"Replica extract: {replica.rows_read} rows in {replica.batches} "
        f"batches; new watermark {replica.new_watermark}; "
        f"truncated={replica.truncated}"
    )

    # 2. Consume the Kafka shard, then replay from a stale checkpoint
    #    (crash before the offset commit) to prove dedup.
    shard = events.assign(
        sequence_number=range(len(events)),
        event_id=events["event_id"],
    )
    first = consume_shard(shard, ShardCheckpoint(shard="shard-0"))
    stale = ShardCheckpoint(
        shard="shard-0",
        sequence_number=-1,
        processed_ids=set(first.checkpoint.processed_ids),
    )
    replay = consume_shard(shard, stale)
    lines.append(
        f"Kafka shard-0: {len(first.new_records)} new records; "
        f"crash-replay skipped {replay.duplicates_skipped} duplicates; "
        f"lag {first.lag}"
    )

    # 3. Lambda ingest with two bad payloads retried separately.
    lam = ingest_lambda_events(
        events.head(50), fail_on={"evt-0003", "evt-0011"}
    )
    lines.append(
        f"Lambda ingest: {len(lam.committed)} committed, "
        f"{len(lam.failed)} failed (retried separately)"
    )

    # 4. Schema drift check on a third-party feed, plus a backfill plan.
    feed = events.head(20).drop(columns=["price"]).assign(agent_id=1)
    drift = detect_schema_drift(
        {
            "event_id": "object",
            "listing_id": "int64",
            "event_type": "object",
            "price": "float64",
            "updated_at": "datetime64[ns, UTC]",
            "event_time": "datetime64[ns, UTC]",
        },
        feed,
    )
    windows = plan_backfill(date(2026, 11, 18), date(2026, 11, 24), chunk_days=7)
    lines.append(f"Third-party feed drift: {drift}")
    lines.append(f"Backfill plan: {len(windows)} windows {windows}")

    # 5. Contract check + Iceberg-style snapshot of the curated table.
    curated = replica.rows[["event_id", "listing_id", "event_type", "price", "event_time"]]
    contract = DataContract(
        dataset="curated_listings",
        owner="data-forge",
        team="Data Forge",
        schema={
            "event_id": "object",
            "listing_id": "int64",
            "event_type": "object",
            "price": "float64",
            "event_time": "datetime64[ns, UTC]",
        },
        freshness_sla_minutes=60,
        min_rows_per_day=100,
        description="Curated listing events for ML, search, and analytics.",
    )
    now = pd.Timestamp("2026-11-25 18:00", tz="UTC")
    violations = validate_contract(
        contract, curated, curated["event_time"].max(), now
    )
    lines.append(
        f"Contract '{contract.dataset}': "
        + ("no violations" if not violations else "; ".join(str(v) for v in violations))
    )
    entry = commit_snapshot(curated, out / "curated_listings", "data-forge daily")
    lines.append(
        f"Snapshot {entry['snapshot_id']} committed: {entry['rows']} rows, "
        f"schema v{entry['schema_version']}"
    )
    kept, expired = expire_snapshots(list_snapshots(out / "curated_listings"), retain=5)
    lines.append(f"Snapshot retention: {len(kept)} kept, {len(expired)} expired")

    # 6. Compaction plan for a table full of small files.
    files = [
        TableFile(f"part-{i:02d}.parquet", 1000, 2 * 1024 * 1024, partition_value("day", "2026-11-25"))
        for i in range(9)
    ]
    plan = plan_compaction(files)
    lines.append(f"Compaction: {plan}")

    # 7. Triage one planted freshness alert, then the same alert again
    #    after its resolution was recorded (feedback loop).
    memory = TriageMemory()
    alert = Alert(
        alert_id="AL-1042",
        source="freshness-monitor",
        message="curated_listings is stale: latest event 95 minutes old",
        metric="latest_event_age_minutes",
        observed=95.0,
        threshold=60.0,
        timestamp=now,
        dataset="curated_listings",
    )
    first_triage = classify_alert(alert, memory)
    lines.append(f"Triage first sight: {first_triage.category} ({first_triage.severity}) — {first_triage.likely_cause}")
    memory.record_resolution(
        alert,
        "replica extractor stalled on a long-running transaction",
        "restarted the extractor from its watermark; added a replica-lag alert",
    )
    second_triage = classify_alert(alert, memory)
    lines.append(
        f"Triage repeat sight: learned={second_triage.learned} — {second_triage.likely_cause}"
    )

    report = "\n".join(lines) + "\n"
    (root / "data_forge_report.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
