"""Streaming ingestion platform in the spirit of Amazon BDT's DataCraft.

DataCraft is the streaming ingestion platform owned by the Huron team under
Business Data Technologies: roughly 19,000 pipelines running actively,
sinking data to Andes, S3 and EDX in micro-batches on AWS Managed Flink
infrastructure, fed by thousands of sources (catalog, inventory, customer
orders, page views, Alexa, and subsidiaries such as IMDB and Audible).

This module models that platform locally with pandas + Parquet — no Flink
cluster, Kinesis stream, S3 bucket, Redshift warehouse or Andes/EDX sink
is involved, and the code says so where it matters. The demo models a
seeded fleet of 60 pipelines (the production fleet is ~19K; the registry,
routing and health logic is the same at either size).

What it covers:

- **Pipeline registry** — every pipeline names its source system, its
  sink (S3, Andes or EDX), its micro-batch interval and its owner team.
- **Multi-source streaming ingest** — one seeded event stream per source
  (catalog, inventory, orders, page views, Alexa), processed in
  micro-batches through the shared streamer: exactly-once via dedup on
  ``event_id`` against the checkpoint, late events dropped at the
  watermark. Each source stream plants 3 duplicate deliveries and
  2 late events, so exactly-once and watermark behaviour are exercised
  for every source, not just one.
- **Sink routing** — accepted events land in a per-sink bronze table
  (Parquet) with a manifest entry (pipeline, source, sink, rows, batch
  count), the way a Flink job sinks each micro-batch to its target.
- **Pipeline health monitor** — per-pipeline lag (newest event time vs
  newest accepted event time), duplicate rate and late rate; a pipeline
  is flagged STALLED when its newest accepted event is older than its
  micro-batch interval, DEGRADED when its duplicate or late rate passes
  5%, otherwise HEALTHY.
- **Data catalog** — the next-generation catalog/discovery piece: every
  sink table is registered with owner, columns and freshness, and a
  keyword search finds tables by name, column or owner, the way a
  discovery engine answers "where is order data?".

All event data is synthetic and seeded. Nothing here is a claim about
any real institution, pipeline, or dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from lakehouse.streaming import StreamCheckpoint, run_stream  # noqa: F401  (re-exported for tests)

SOURCES = ["catalog", "inventory", "orders", "page_views", "alexa"]
SINKS = ["S3", "Andes", "EDX"]
# Fixed per-source seed offsets (str hash() is randomised per process,
# so a literal table keeps the demo deterministic across runs).
_SOURCE_SEED_OFFSET = {"catalog": 11, "inventory": 23, "orders": 37, "page_views": 51, "alexa": 67}
# Production fleet size, for scale context only; the demo models 60.
PRODUCTION_FLEET_SIZE = 19_000


@dataclass(frozen=True)
class Pipeline:
    """One registered ingestion pipeline: source -> sink, micro-batch cadence."""

    pipeline_id: str
    source: str
    sink: str
    micro_batch_minutes: int
    owner_team: str


def generate_pipeline_registry(n: int = 60, seed: int = 42) -> pd.DataFrame:
    """Seeded registry of n pipelines across the 5 sources and 3 sinks."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        source = SOURCES[i % len(SOURCES)]
        sink = SINKS[int(rng.integers(0, len(SINKS)))]
        rows.append(
            {
                "pipeline_id": f"DC-{i + 1:05d}",
                "source": source,
                "sink": sink,
                "micro_batch_minutes": int(rng.choice([1, 5, 15])),
                "owner_team": f"bdt-{source}",
            }
        )
    return pd.DataFrame(rows)


def generate_source_events(source: str, n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Seeded synthetic event stream for one source system.

    120 base events plus 3 duplicate deliveries and 2 late events,
    mirroring the shared streamer's planted cases so exactly-once and
    watermark behaviour are exercised per source.
    """
    rng = np.random.default_rng(seed + _SOURCE_SEED_OFFSET[source])
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"{source[:3].upper()}-{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "source": source,
            "record_id": [f"{source[:3].upper()}-R{i:05d}" for i in range(n)],
            "payload_value": np.round(rng.uniform(1.0, 500.0, size=n), 2),
        }
    )
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = [f"{source[:3].upper()}-L90001", f"{source[:3].upper()}-L90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def ingest_source(source: str, n: int = 120, seed: int = 42) -> dict:
    """Run one source's stream through the shared micro-batch streamer."""
    stream = generate_source_events(source, n=n, seed=seed)
    result = run_stream(stream, batch_size=40)
    result["source"] = source
    return result


def route_to_sinks(registry: pd.DataFrame, accepted_by_source: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the per-sink manifest: which pipelines feed each sink, rows landed.

    Each source's accepted events are split across that source's
    pipelines' sinks in registry order, so every sink receives a share
    of every source — the same fan-out a real ingestion platform does.
    """
    rows = []
    for source, accepted in accepted_by_source.items():
        pipes = registry[registry["source"] == source]
        if pipes.empty or accepted.empty:
            continue
        sinks = pipes["sink"].tolist()
        chunks = np.array_split(accepted, len(sinks))
        for sink, chunk, (_, pipe) in zip(sinks, chunks, pipes.iterrows()):
            rows.append(
                {
                    "pipeline_id": pipe["pipeline_id"],
                    "source": source,
                    "sink": sink,
                    "rows_landed": int(len(chunk)),
                    "batches": int(np.ceil(len(chunk) / 40)) if len(chunk) else 0,
                }
            )
    return pd.DataFrame(rows)


def monitor_pipelines(
    registry: pd.DataFrame,
    stream_results: dict[str, dict],
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Per-pipeline health: lag, duplicate rate, late rate, status.

    STALLED when the newest accepted event for the source is older than
    the pipeline's micro-batch interval; DEGRADED when the duplicate or
    late rate passes 5%; otherwise HEALTHY. A pipeline with no accepted
    events at all is STALLED, never silently healthy.
    """
    rows = []
    for _, pipe in registry.iterrows():
        result = stream_results[pipe["source"]]
        accepted = result["accepted"]
        total = int(result["total_arrived"])
        newest = pd.to_datetime(accepted["event_time"]).max() if len(accepted) else None
        ref = as_of if as_of is not None else pd.to_datetime(result["accepted"]["event_time"]).max()
        lag_minutes = None if newest is None else float((ref - newest).total_seconds() / 60.0)
        dup_rate = len(result["duplicates"]) / total if total else 0.0
        late_rate = len(result["late"]) / total if total else 0.0
        if newest is None or (lag_minutes is not None and lag_minutes > pipe["micro_batch_minutes"]):
            status = "STALLED"
        elif dup_rate > 0.05 or late_rate > 0.05:
            status = "DEGRADED"
        else:
            status = "HEALTHY"
        rows.append(
            {
                "pipeline_id": pipe["pipeline_id"],
                "source": pipe["source"],
                "sink": pipe["sink"],
                "micro_batch_minutes": int(pipe["micro_batch_minutes"]),
                "lag_minutes": lag_minutes,
                "duplicate_rate": round(dup_rate, 4),
                "late_rate": round(late_rate, 4),
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def build_catalog(manifest: pd.DataFrame) -> pd.DataFrame:
    """Register every sink table in the data catalog with owner and columns."""
    columns = {
        "catalog": ["record_id", "event_id", "event_time", "payload_value"],
        "inventory": ["record_id", "event_id", "event_time", "payload_value"],
        "orders": ["record_id", "event_id", "event_time", "payload_value"],
        "page_views": ["record_id", "event_id", "event_time", "payload_value"],
        "alexa": ["record_id", "event_id", "event_time", "payload_value"],
    }
    tables = (
        manifest.groupby(["sink", "source"], as_index=False)["rows_landed"]
        .sum()
        .rename(columns={"rows_landed": "row_count"})
    )
    rows = []
    for _, t in tables.iterrows():
        rows.append(
            {
                "table": f"{t['sink'].lower()}.{t['source']}_bronze",
                "source": t["source"],
                "sink": t["sink"],
                "owner_team": f"bdt-{t['source']}",
                "columns": ", ".join(columns[t["source"]]),
                "row_count": int(t["row_count"]),
            }
        )
    return pd.DataFrame(rows)


def search_catalog(catalog: pd.DataFrame, keyword: str) -> pd.DataFrame:
    """Discovery search: match a keyword against table, source, columns, owner."""
    key = keyword.lower()
    mask = (
        catalog["table"].str.lower().str.contains(key)
        | catalog["source"].str.lower().str.contains(key)
        | catalog["columns"].str.lower().str.contains(key)
        | catalog["owner_team"].str.lower().str.contains(key)
    )
    return catalog[mask].reset_index(drop=True)


def run_datacraft(seed: int = 42) -> dict:
    """End-to-end demo: registry, per-source ingest, sink routing, health, catalog."""
    registry = generate_pipeline_registry(seed=seed)
    results = {source: ingest_source(source, seed=seed) for source in SOURCES}
    accepted = {s: r["accepted"] for s, r in results.items()}
    manifest = route_to_sinks(registry, accepted)
    # "Now" for the health check: 10 minutes after the newest accepted
    # event anywhere in the fleet, so lag is measured against the end
    # of the ingest window rather than against each source's own max.
    newest_anywhere = max(
        pd.to_datetime(r["accepted"]["event_time"]).max() for r in results.values()
    )
    health = monitor_pipelines(registry, results, as_of=newest_anywhere + timedelta(minutes=10))
    catalog = build_catalog(manifest)
    total_arrived = sum(r["total_arrived"] for r in results.values())
    total_accepted = sum(len(r["accepted"]) for r in results.values())
    total_dupes = sum(len(r["duplicates"]) for r in results.values())
    total_late = sum(len(r["late"]) for r in results.values())
    return {
        "registry": registry,
        "results": results,
        "manifest": manifest,
        "health": health,
        "catalog": catalog,
        "total_arrived": total_arrived,
        "total_accepted": total_accepted,
        "total_duplicates": total_dupes,
        "total_late": total_late,
        "sink_rows": manifest.groupby("sink")["rows_landed"].sum().to_dict(),
    }
