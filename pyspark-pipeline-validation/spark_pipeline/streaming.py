"""Streaming + CDC layer for the PySpark pipeline: Kafka-style micro-batches.

Mirrors a Spark Structured Streaming job reading a Kafka topic, with
change-data-capture upserts into a curated table:

  topic (JSON lines)   -> local ``events.jsonl`` standing in for a Kafka topic
  micro-batch          -> one file segment per batch, processed in offset order
  watermark            -> events at or before the watermark are late and dropped
  CDC apply            -> insert / update / delete by event_id, latest wins
                         (mirrors a Delta Lake MERGE INTO on event_id)
  data contract        -> every record checked before apply; bad records go
                         to the dead-letter queue, never into the curated table
  backfill             -> replaying the topic from offset 0 rebuilds the same
                         curated state; a run report records the replay

Nothing here calls a real Kafka broker, Spark cluster, or Delta Lake
runtime. pandas + JSON lines are the local stand-ins, and every function
names the Spark / Delta operation it mirrors. All events are synthetic
and seeded (seed 42), so every run produces the same stream.
"""
import json
from pathlib import Path

import pandas as pd

SEED = 42
TOPIC = "events-cdc"
WATERMARK_LAG_SECONDS = 300  # 5 minutes, like a streaming watermark

CONTRACT_REQUIRED = ["event_id", "op", "event_time", "ingested_at"]
VALID_OPS = ("c", "u", "d")  # create / update / delete


def generate_cdc_stream(seed=SEED):
    """Deterministic CDC event stream: 3 micro-batches, 50 events.

    Batch 1: 20 inserts (EVT-100001..EVT-100020).
    Batch 2: 10 updates to batch-1 rows, 5 new inserts, 2 deletes.
    Batch 3: 5 updates, 3 deletes, 1 late event (before the watermark),
             4 invalid records (bad op, missing key, bad amount, bad date)
             that must land in the dead-letter queue, not the table.
    """
    rng = __import__("numpy").random.default_rng(seed)
    events = []

    def ev(event_id, op, batch, minute, **fields):
        rec = {
            "event_id": event_id,
            "op": op,
            "event_time": f"2026-11-17T10:{minute:02d}:00",
            "ingested_at": f"2026-11-17T10:{minute:02d}:30",
            "batch": batch,
        }
        rec.update(fields)
        return rec

    products = ["P100", "P200", "P300", "P400"]
    price = {"P100": 49.99, "P200": 29.99, "P300": 19.99, "P400": 39.99}
    for i in range(20):
        code = products[i % 4]
        qty = int(rng.integers(1, 6))
        events.append(ev(f"EVT-100{i + 1:03d}", "c", 1, i,
                         user_id=f"U{int(rng.integers(1000, 9999))}",
                         product_code=code, region=["North", "South", "East", "West"][i % 4],
                         channel=["web", "mobile", "store"][i % 3],
                         event_date="2026-11-17", quantity=qty,
                         unit_price=price[code], amount=round(qty * price[code], 2)))
    for i in range(10):
        code = products[i % 4]
        qty = int(rng.integers(1, 6))
        events.append(ev(f"EVT-100{i + 1:03d}", "u", 2, 20 + i,
                         user_id=f"U{int(rng.integers(1000, 9999))}",
                         product_code=code, region="North",
                         channel="web", event_date="2026-11-17", quantity=qty,
                         unit_price=price[code], amount=round(qty * price[code], 2)))
    for i in range(5):
        code = products[i % 4]
        qty = int(rng.integers(1, 6))
        events.append(ev(f"EVT-100{21 + i:03d}", "c", 2, 30 + i,
                         user_id=f"U{int(rng.integers(1000, 9999))}",
                         product_code=code, region="South",
                         channel="mobile", event_date="2026-11-17", quantity=qty,
                         unit_price=price[code], amount=round(qty * price[code], 2)))
    for i in range(2):
        events.append(ev(f"EVT-100{11 + i:03d}", "d", 2, 35 + i))
    for i in range(5):
        code = products[i % 4]
        qty = int(rng.integers(1, 6))
        events.append(ev(f"EVT-100{i + 1:03d}", "u", 3, 40 + i,
                         user_id=f"U{int(rng.integers(1000, 9999))}",
                         product_code=code, region="East",
                         channel="store", event_date="2026-11-17", quantity=qty,
                         unit_price=price[code], amount=round(qty * price[code], 2)))
    for i in range(3):
        events.append(ev(f"EVT-100{16 + i:03d}", "d", 3, 45 + i))
    # One late event: event_time 09:00, before the batch-3 watermark (10:40).
    events.append(ev("EVT-100001", "u", 3, 48, user_id="U1111",
                     product_code="P100", region="North", channel="web",
                     event_date="2026-11-17", quantity=1,
                     unit_price=49.99, amount=49.99,
                     event_time="2026-11-17T09:00:00"))
    # Four invalid records for the dead-letter queue.
    bad_op = ev("EVT-100099", "x", 3, 50, user_id="U2222",
                product_code="P100", region="North", channel="web",
                event_date="2026-11-17", quantity=1, unit_price=49.99, amount=49.99)
    events.append(bad_op)
    no_key = ev("EVT-100098", "c", 3, 51, product_code="P100",
                region="North", channel="web", event_date="2026-11-17",
                quantity=1, unit_price=49.99, amount=49.99)
    # No user_id on purpose: the data contract must catch the missing key.
    events.append(no_key)
    bad_amount = ev("EVT-100097", "c", 3, 52, user_id="U3333",
                    product_code="P100", region="North", channel="web",
                    event_date="2026-11-17", quantity=2, unit_price=49.99, amount=-5.00)
    events.append(bad_amount)
    bad_date = ev("EVT-100096", "c", 3, 53, user_id="U4444",
                  product_code="P100", region="North", channel="web",
                  event_date="2027-01-15", quantity=1, unit_price=49.99, amount=49.99)
    events.append(bad_date)
    return events


def validate_contract(record):
    """Data-contract check for one CDC record. Returns a list of violations.

    Mirrors a schema + contract check on the streaming source before any
    write: required fields, valid op, and for create/update rows the same
    value rules the batch pipeline enforces (non-negative amount, in-window
    date, amount == quantity * unit_price).
    """
    problems = []
    for field in CONTRACT_REQUIRED:
        if field not in record or record[field] in (None, ""):
            problems.append(f"missing field: {field}")
    if problems:
        return problems
    if record["op"] not in VALID_OPS:
        problems.append(f"unknown op: {record['op']}")
        return problems
    if record["op"] == "d":
        return problems
    if record.get("user_id") in (None, ""):
        problems.append("missing field: user_id")
    if record.get("amount") is not None and record["amount"] < 0:
        problems.append("amount is negative")
    if record.get("event_date") not in (None, "") and not (
        "2026-10-01" <= record["event_date"] <= "2026-11-17"
    ):
        problems.append(f"event_date out of window: {record['event_date']}")
    if None not in (record.get("quantity"), record.get("unit_price"), record.get("amount")):
        if abs(record["amount"] - record["quantity"] * record["unit_price"]) > 0.01:
            problems.append("amount != quantity * unit_price")
    return problems


def apply_cdc(state, events, watermark):
    """Apply one micro-batch of CDC events to the curated state table.

    Mirrors Delta Lake ``MERGE INTO ... WHEN MATCHED THEN UPDATE / DELETE,
    WHEN NOT MATCHED THEN INSERT`` keyed on event_id, with a streaming
    watermark: events with event_time at or before the watermark are late
    and dropped. Returns (new_state, counts, dead_letter_rows).
    """
    counts = {"inserts": 0, "updates": 0, "deletes": 0,
              "late_dropped": 0, "dlq": 0}
    dlq_rows = []
    state = state.copy()
    idx = {eid: i for i, eid in enumerate(state["event_id"])} if len(state) else {}
    for rec in events:
        problems = validate_contract(rec)
        if problems:
            counts["dlq"] += 1
            dlq_rows.append({**rec, "violation": "; ".join(problems)})
            continue
        if rec["event_time"] <= watermark:
            counts["late_dropped"] += 1
            continue
        eid = rec["event_id"]
        if rec["op"] == "d":
            if eid in idx:
                state = state.drop(index=idx[eid]).reset_index(drop=True)
                idx = {e: i for i, e in enumerate(state["event_id"])}
                counts["deletes"] += 1
            continue
        row = {k: v for k, v in rec.items() if k not in ("op", "batch")}
        if eid in idx:
            for col, val in row.items():
                state.at[idx[eid], col] = val
            counts["updates"] += 1
        else:
            if len(state) == 0:
                state = pd.DataFrame([row])
            else:
                state = pd.concat([state, pd.DataFrame([row])], ignore_index=True)
            idx[eid] = len(state) - 1
            counts["inserts"] += 1
    return state, counts, dlq_rows


def run_streaming(out_dir, seed=SEED):
    """Run the full streaming job: write the topic, process 3 micro-batches.

    Watermark advances to (max event_time seen so far minus the 5-minute
    lag) after each batch, so the late event in batch 3 is dropped.
    Returns (summary, state, dlq_frame).
    """
    out_dir = Path(out_dir)
    tables = out_dir / "streaming_tables"
    tables.mkdir(parents=True, exist_ok=True)

    events = generate_cdc_stream(seed)
    topic_path = tables / "events.jsonl"
    with open(topic_path, "w") as fh:
        for rec in events:
            fh.write(json.dumps(rec) + "\n")

    columns = ["event_id", "user_id", "product_code", "region", "channel",
               "event_date", "quantity", "unit_price", "amount",
               "event_time", "ingested_at"]
    state = pd.DataFrame(columns=columns)
    watermark = "0000-00-00T00:00:00"
    totals = {"inserts": 0, "updates": 0, "deletes": 0,
              "late_dropped": 0, "dlq": 0}
    all_dlq = []
    batch_counts = {}
    for batch in (1, 2, 3):
        batch_events = [r for r in events if r["batch"] == batch]
        state, counts, dlq_rows = apply_cdc(state, batch_events, watermark)
        batch_counts[batch] = counts
        all_dlq.extend(dlq_rows)
        for key in totals:
            totals[key] += counts[key]
        # Advance the watermark: max event_time seen minus the 5-minute lag.
        seen = [r["event_time"] for r in events if r["batch"] <= batch]
        latest = max(seen)
        hh, mm = int(latest[11:13]), int(latest[14:16])
        total_min = hh * 60 + mm - WATERMARK_LAG_SECONDS // 60
        watermark = f"2026-11-17T{total_min // 60:02d}:{total_min % 60:02d}:00"

    state.to_parquet(tables / "curated_streaming.parquet", index=False)
    dlq = pd.DataFrame(all_dlq)
    if len(dlq):
        dlq.to_parquet(tables / "dead_letter.parquet", index=False)
    summary = {
        "events": len(events),
        "micro_batches": 3,
        "final_rows": len(state),
        "final_revenue": round(float(state["amount"].sum()), 2) if len(state) else 0.0,
        "watermark": watermark,
        **totals,
        "batch_counts": batch_counts,
    }
    return summary, state, dlq


def orchestrate(out_dir):
    """Minimal workflow orchestration for the batch + streaming job.

    Mirrors a workflow DAG (Airflow-style): ingest -> batch pipeline ->
    streaming CDC -> quality checks -> publish, each step retried once on
    failure. Returns the ordered run log.
    """
    from .pipeline import run_pipeline

    log = []

    def step(name, fn):
        for attempt in (1, 2):
            try:
                result = fn()
                log.append({"step": name, "status": "OK", "attempt": attempt,
                            "detail": result})
                return result
            except Exception as exc:  # noqa: BLE001 - retried once, then logged
                if attempt == 2:
                    log.append({"step": name, "status": "FAIL", "attempt": attempt,
                                "detail": str(exc)})
                    raise
    step("ingest_topic", lambda: f"{len(generate_cdc_stream())} CDC events")
    summary, _, _ = step("batch_pipeline", lambda: run_pipeline(out_dir))
    step("batch_checks",
         lambda: f"{summary['checks_passed']}/{summary['checks_total']} checks passed")
    stream_summary, _, _ = step("streaming_cdc", lambda: run_streaming(out_dir))
    step("publish_curated",
         lambda: (f"batch gold={summary['gold_rows']} rows, "
                  f"streaming state={stream_summary['final_rows']} rows, "
                  f"dlq={stream_summary['dlq']}"))
    return log
