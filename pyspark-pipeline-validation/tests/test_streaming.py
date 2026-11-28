"""Tests for the streaming CDC layer: upserts, deletes, watermark, DLQ, backfill."""
import pandas as pd
import pytest

from spark_pipeline.streaming import (
    apply_cdc,
    generate_cdc_stream,
    orchestrate,
    run_streaming,
    validate_contract,
)

COLUMNS = ["event_id", "user_id", "product_code", "region", "channel",
           "event_date", "quantity", "unit_price", "amount",
           "event_time", "ingested_at"]


def empty_state():
    return pd.DataFrame(columns=COLUMNS)


def base_event(event_id="EVT-1", op="c", event_time="2026-11-17T10:00:00"):
    return {"event_id": event_id, "op": op, "event_time": event_time,
            "ingested_at": "2026-11-17T10:00:30", "batch": 1,
            "user_id": "U1234", "product_code": "P100", "region": "North",
            "channel": "web", "event_date": "2026-11-17", "quantity": 2,
            "unit_price": 49.99, "amount": 99.98}


def test_stream_is_deterministic():
    assert generate_cdc_stream() == generate_cdc_stream()
    assert len(generate_cdc_stream()) == 50


def test_insert_then_update_keeps_latest():
    state, counts, _ = apply_cdc(empty_state(), [base_event()], "0000-00-00T00:00:00")
    assert counts["inserts"] == 1 and len(state) == 1
    updated = base_event(event_id="EVT-1", op="u",
                         event_time="2026-11-17T10:05:00")
    updated["quantity"] = 3
    updated["amount"] = 149.97
    state, counts, _ = apply_cdc(state, [updated], "0000-00-00T00:00:00")
    assert counts["updates"] == 1 and len(state) == 1
    assert float(state.iloc[0]["amount"]) == 149.97


def test_delete_removes_row_and_unknown_delete_is_noop():
    state, _, _ = apply_cdc(empty_state(), [base_event()], "0000-00-00T00:00:00")
    state, counts, _ = apply_cdc(
        state, [base_event(event_id="EVT-1", op="d",
                           event_time="2026-11-17T10:05:00")],
        "0000-00-00T00:00:00")
    assert counts["deletes"] == 1 and len(state) == 0
    state, counts, _ = apply_cdc(
        state, [base_event(event_id="EVT-9", op="d",
                           event_time="2026-11-17T10:06:00")],
        "0000-00-00T00:00:00")
    assert counts["deletes"] == 0 and len(state) == 0


def test_late_event_is_dropped():
    state, counts, _ = apply_cdc(
        empty_state(), [base_event(event_time="2026-11-17T09:00:00")],
        "2026-11-17T10:31:00")
    assert counts["late_dropped"] == 1 and len(state) == 0


def test_contract_rejects_bad_op_missing_key_negative_amount_bad_date():
    bad_op = base_event(op="x")
    assert any("unknown op" in p for p in validate_contract(bad_op))
    no_key = base_event()
    del no_key["user_id"]
    assert any("user_id" in p for p in validate_contract(no_key))
    bad_amount = base_event()
    bad_amount["amount"] = -5.00
    assert any("negative" in p for p in validate_contract(bad_amount))
    bad_date = base_event()
    bad_date["event_date"] = "2027-01-15"
    assert any("out of window" in p for p in validate_contract(bad_date))
    assert validate_contract(base_event()) == []


def test_invalid_records_go_to_dlq_not_the_table():
    state, counts, dlq = apply_cdc(
        empty_state(), [base_event(op="x"), base_event(event_id="EVT-2")],
        "0000-00-00T00:00:00")
    assert counts["dlq"] == 1 and len(dlq) == 1 and len(state) == 1
    assert dlq[0]["event_id"] == "EVT-1"


def test_full_run_counts():
    summary, state, dlq = run_streaming(__import__("pathlib").Path("/tmp"))
    assert summary["events"] == 50
    assert summary["inserts"] == 25
    assert summary["updates"] == 15
    assert summary["deletes"] == 5
    assert summary["late_dropped"] == 1
    assert summary["dlq"] == 4
    assert summary["final_rows"] == 20
    assert len(dlq) == 4
    assert state["event_id"].is_unique
    assert (state["amount"] >= 0).all()


def test_backfill_replay_rebuilds_same_state(tmp_path):
    summary1, state1, _ = run_streaming(tmp_path / "run1")
    summary2, state2, _ = run_streaming(tmp_path / "run2")
    assert summary1["final_rows"] == summary2["final_rows"]
    assert summary1["final_revenue"] == summary2["final_revenue"]
    assert state1.sort_values("event_id").reset_index(drop=True).equals(
        state2.sort_values("event_id").reset_index(drop=True))


def test_orchestration_runs_all_steps_in_order(tmp_path):
    log = orchestrate(tmp_path)
    names = [entry["step"] for entry in log]
    assert names == ["ingest_topic", "batch_pipeline", "batch_checks",
                     "streaming_cdc", "publish_curated"]
    assert all(entry["status"] == "OK" for entry in log)
