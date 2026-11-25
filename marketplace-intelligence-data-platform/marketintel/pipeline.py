"""DAG orchestration with run state, retries, and recovery.

Tasks declare dependencies; the runner executes them in topological
order, retries a failed task once, and records every attempt in the
warehouse's run_state table. A run that fails mid-way can resume: tasks
already marked done are skipped on the next run instead of re-running.
Airflow equivalent: a DAG with task dependencies, one retry, and a
run-id-scoped state store. The runner here is deliberately small so the
dependency and recovery logic is visible and testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import contracts, quality, schema_mapping, warehouse


@dataclass
class Task:
    name: str
    fn: object
    depends_on: list = field(default_factory=list)


def topological_order(tasks):
    by_name = {t.name: t for t in tasks}
    order, visiting, done = [], set(), set()

    def visit(name):
        if name in done:
            return
        if name in visiting:
            raise ValueError(f"dependency cycle at task {name}")
        visiting.add(name)
        for dep in by_name[name].depends_on:
            if dep not in by_name:
                raise ValueError(f"task {name} depends on unknown task {dep}")
            visit(dep)
        visiting.discard(name)
        done.add(name)
        order.append(name)

    for task in tasks:
        visit(task.name)
    return [by_name[n] for n in order]


def run_dag(tasks, conn, run_id):
    """Run tasks in dependency order with one retry each. Returns a
    dict of task name -> 'done' | 'failed' | 'skipped'. Completed tasks
    from an earlier run of the same run_id are skipped (recovery)."""
    results = {}
    for task in topological_order(tasks):
        row = conn.execute(
            "SELECT status FROM run_state WHERE run_id = ? AND task = ?",
            (run_id, task.name),
        ).fetchone()
        if row and row[0] == "done":
            results[task.name] = "skipped"
            continue
        if any(results.get(d) == "failed" for d in task.depends_on):
            results[task.name] = "failed"
            continue
        last_error = None
        for _attempt in range(2):  # first try + one retry
            try:
                task.fn()
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - retry then record
                last_error = exc
        status = "done" if last_error is None else "failed"
        conn.execute(
            "INSERT OR REPLACE INTO run_state (run_id, task, status, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (run_id, task.name, status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        results[task.name] = status
        if status == "failed":
            raise RuntimeError(
                f"task {task.name} failed after retry: {last_error}"
            )
    return results


MARKET_CONTRACT = contracts.DataContract(
    name="market_snapshot",
    required_fields=["competitor", "zone", "snapshot_date", "price_usd"],
    optional_fields=["demand_index", "surge_multiplier", "service"],
    freshness_hours=24.0,
    min_completeness=0.90,
)


def run_pipeline(data_dir, db_path, run_id="daily", as_of="2026-11-25T00:00:00"):
    """Full pipeline: ingest -> map -> contract -> quality -> load ->
    reconcile -> publish. Returns a JSON-serialisable report dict."""
    from pathlib import Path

    from .sources import CsvFeedSource, InternalAggregateSource, JsonApiSource, load_json_pages

    data_dir = Path(data_dir)
    conn = warehouse.connect(db_path)
    state = {}

    def ingest():
        v1 = CsvFeedSource(
            "competitor_prices_v1", data_dir / "competitor_prices_v1.csv", "v1"
        ).fetch(ingested_at=as_of)
        v2 = CsvFeedSource(
            "competitor_prices_v2", data_dir / "competitor_prices_v2.csv", "v2"
        ).fetch(ingested_at=as_of)
        pages = load_json_pages(data_dir / "demand_signals.json")
        api = JsonApiSource(
            "demand_signals_api", pages, "v1", fail_on_page=1
        ).fetch(ingested_at=as_of)
        internal = InternalAggregateSource(
            "internal_trips",
            [
                {"competitor": "uber", "zone": "downtown", "snapshot_date": "2026-11-24",
                 "price_usd": "18.50", "service": "ride"},
                {"competitor": "uber", "zone": "airport", "snapshot_date": "2026-11-24",
                 "price_usd": "32.00", "service": "ride"},
            ],
            "v1",
        ).fetch(ingested_at=as_of)
        state["raw"] = v1.records + v2.records + api.records + internal.records
        state["api_retries"] = api.retries
        state["api_pages"] = api.pages_fetched

    def map_sources():
        mapped, reports, review = [], [], schema_mapping.ReviewQueue()
        for rec in state["raw"]:
            row, report = schema_mapping.map_record(rec.payload)
            row["source"] = rec.source
            row["ingested_at"] = rec.ingested_at
            reports.append(report)
            for src_f, tgt_f, conf in report.needs_review:
                review.add(src_f, tgt_f, conf, record_ref=rec.source)
            if report.ok:
                mapped.append(row)
            else:
                row["_mapping_errors"] = report.validation_errors
                mapped.append(row)  # quality stage quarantines it
        state["mapped"] = mapped
        state["review_queue"] = review
        state["unmapped_fields"] = sorted(
            {f for r in reports for f in r.unmapped}
        )

    def check_contract():
        # The contract runs on MAPPED rows: renames such as fare_usd ->
        # price_usd are resolved by the mapper first, so a source rename
        # is not a breaking change at the contract layer. Schema
        # evolution across raw versions is covered by unit tests.
        state["contract"] = contracts.check_batch(
            MARKET_CONTRACT, state["mapped"], as_of=as_of
        )

    def check_quality():
        known = {"downtown", "airport", "suburbs", "university", "waterfront"}
        loaded, report = quality.run_quality_checks(
            state["mapped"],
            watermark_date=warehouse.get_watermark(conn),
            known_zones=known,
        )
        state["loaded_rows"] = loaded
        state["quality"] = report

    def load():
        inserted, skipped = warehouse.load_rows(conn, state["loaded_rows"])
        state["inserted"] = inserted
        state["skipped"] = skipped

    def reconcile():
        state["reconciliation"] = quality.reconcile(
            state["loaded_rows"],
            warehouse.fact_count(conn),
            warehouse.fact_price_total(conn),
        )

    def publish():
        from .catalog import generate_catalog

        state["catalog"] = generate_catalog(conn)

    tasks = [
        Task("ingest", ingest),
        Task("map", map_sources, ["ingest"]),
        Task("contract", check_contract, ["map"]),
        Task("quality", check_quality, ["contract"]),
        Task("load", load, ["quality"]),
        Task("reconcile", reconcile, ["load"]),
        Task("publish", publish, ["reconcile"]),
    ]
    dag_results = run_dag(tasks, conn, run_id)
    report = {
        "run_id": run_id,
        "raw_records": len(state["raw"]),
        "mapped_records": len(state["mapped"]),
        "api_pages_fetched": state["api_pages"],
        "api_retries": state["api_retries"],
        "unmapped_fields": state["unmapped_fields"],
        "review_queue_pending": len(state["review_queue"].pending()),
        "contract": {
            "completeness": round(state["contract"].completeness, 4),
            "errors": state["contract"].errors,
            "additive_changes": state["contract"].additive_changes,
            "breaking_changes": state["contract"].breaking_changes,
        },
        "quality": state["quality"].to_dict(),
        "inserted": state["inserted"],
        "skipped_on_load": state["skipped"],
        "reconciliation": state["reconciliation"].to_dict(),
        "catalog": state["catalog"],
        "dag": dag_results,
        "daily_avg_price": [
            {"zone": z, "date": d, "avg_price": p, "n": n}
            for z, d, p, n in warehouse.daily_average_price(conn)
        ],
    }
    conn.close()
    return report
