"""Pipeline orchestration: topic -> micro-batches -> quality -> warehouse.

One run: seed (or receive) order events, produce them to the Kafka-modelled
topic, poll micro-batches, cleanse + aggregate each batch, write facts to
the partitioned warehouse, and finish with a governance report. Run state
(batch id, rows, quarantine counts) is recorded so a failed batch can be
retried from its last committed offset.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import pandas as pd

from .events import KafkaTopic, OrderEvent, seed_events
from .governance import check_access, check_master_data, check_sla
from .streaming import run_micro_batch, split_batches
from .warehouse import dim_menu_item_scd2, dim_restaurant, fact_rows, write_fact


@dataclass
class RunState:
    batches: int = 0
    produced: int = 0
    clean: int = 0
    quarantined: int = 0
    late: int = 0
    partitions_written: int = 0
    errors: list[str] = field(default_factory=list)


def run_pipeline(events: list[OrderEvent] | None = None, warehouse_dir: str = "warehouse",
                 out_dir: str = "out") -> tuple[RunState, dict]:
    """Run the full pipeline end to end. Returns (run state, governance report)."""
    events = events if events is not None else seed_events()
    state = RunState(produced=len(events))
    topic = KafkaTopic("restaurant-orders")
    for event in events:
        topic.produce(event)

    os.makedirs(warehouse_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    all_clean: list[OrderEvent] = []
    quarantine_rows: list[dict] = []
    consumed = topic.poll("order-pipeline", max_records=10_000)
    batches = split_batches(consumed)
    for batch in batches:
        try:
            quality, _agg = run_micro_batch(batch)
        except Exception as exc:  # noqa: BLE001 - record and continue to next batch
            state.errors.append(f"batch {batch.batch_id}: {exc}")
            continue
        state.batches += 1
        state.clean += len(quality.clean)
        state.quarantined += len(quality.quarantined)
        state.late += len(batch.late)
        all_clean.extend(quality.clean)
        quarantine_rows.extend(
            {
                "order_id": e.order_id, "restaurant_id": e.restaurant_id,
                "event_time": e.event_time.isoformat(), "reason": reason,
            }
            for e, reason in quality.quarantined
        )
    topic.commit("order-pipeline", consumed)

    fact = fact_rows(all_clean)
    written = write_fact(fact, warehouse_dir)
    state.partitions_written = len(written)
    dim_restaurant().to_parquet(os.path.join(warehouse_dir, "dim_restaurant.parquet"), index=False)
    dim_menu_item_scd2().to_parquet(os.path.join(warehouse_dir, "dim_menu_item.parquet"), index=False)
    pd.DataFrame(quarantine_rows).to_parquet(
        os.path.join(warehouse_dir, "order_quarantine.parquet"), index=False
    )

    report = {
        "master_data_ok": check_master_data(fact),
        "sla": check_sla(
            state.clean, state.quarantined, state.late, state.produced,
            unique_total=len({e.order_id for e in events}),
        ),
        "access_violations": (
            []
            if check_access("data-engineer", "order_quarantine")
            and not check_access("analyst", "order_quarantine")
            else ["role access rules do not hold for order_quarantine"]
        ),
        "topic_lag_after_commit": topic.lag("order-pipeline"),
    }
    with open(os.path.join(out_dir, "run_state.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "batches": state.batches, "produced": state.produced,
                "clean": state.clean, "quarantined": state.quarantined,
                "late": state.late, "partitions_written": state.partitions_written,
                "errors": state.errors, "governance": report,
            },
            fh, indent=2,
        )
    return state, report
