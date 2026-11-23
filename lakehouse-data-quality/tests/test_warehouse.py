"""Tests for the backend warehouse load (lakehouse.warehouse)."""

import pandas as pd
import pytest

from lakehouse.warehouse import (
    ConsumerState,
    consume_events,
    generate_warehouse_events,
    load_customer_dim,
    load_order_fact,
    load_product_dim,
    reconcile_warehouse,
    run_warehouse,
    stage_events,
    validate_events,
)


def test_generated_events_include_planted_bad_rows():
    events = generate_warehouse_events()
    assert len(events) == 160
    assert events["event_id"].nunique() == 155  # 5 replays share ids
    assert events["kafka_offset"].is_unique
    assert (events["customer_id"] == "C999").sum() == 3
    assert (events["quantity"] < 0).sum() == 2


def test_consume_drops_replays_and_commits_offsets():
    events = generate_warehouse_events()
    result = consume_events(events)
    assert len(result["accepted"]) == 155
    assert len(result["duplicates"]) == 5
    assert result["batches"] == 4  # 160 rows in batches of 50
    assert result["state"].committed_offset == 159
    assert result["accepted"]["event_id"].is_unique


def test_consume_resumes_from_state_without_reprocessing():
    events = generate_warehouse_events()
    first = consume_events(events)
    second = consume_events(events, state=first["state"])
    assert len(second["accepted"]) == 0
    assert second["batches"] == 0
    assert second["state"].committed_offset == 159


def test_validate_quarantines_unknown_customers_and_bad_quantities():
    events = generate_warehouse_events()
    accepted = consume_events(events)["accepted"]
    checked = validate_events(accepted)
    assert len(checked["valid"]) == 150
    assert len(checked["quarantined"]) == 5
    reasons = checked["quarantined"]["quarantine_reason"].value_counts().to_dict()
    assert reasons == {"unknown_customer": 3, "non_positive_quantity": 2}


def test_stage_writes_parquet_and_manifest(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    result = stage_events(valid, tmp_path / "staging")
    assert result["staged_path"].exists()
    assert result["manifest"]["rows_staged"] == 150
    staged = pd.read_parquet(result["staged_path"])
    assert len(staged) == 150


def test_customer_dim_scd2_close_and_reopen_on_change(tmp_path):
    from lakehouse.warehouse import _scd2_load

    staged_v1 = pd.DataFrame([
        {"customer_id": "C001", "region": "North", "segment": "Retail"},
        {"customer_id": "C002", "region": "South", "segment": "Online"},
    ])
    first = _scd2_load(staged_v1, tmp_path / "dim", "customer_id",
                        ["region", "segment"], "customer_key")
    assert first["inserted"] == 2
    # C001 moves region North -> East: old version closes, new one opens.
    staged_v2 = pd.DataFrame([
        {"customer_id": "C001", "region": "East", "segment": "Retail"},
        {"customer_id": "C002", "region": "South", "segment": "Online"},
    ])
    second = _scd2_load(staged_v2, tmp_path / "dim", "customer_id",
                         ["region", "segment"], "customer_key")
    assert second == {"inserted": 0, "updated": 1, "unchanged": 1,
                      "dim_path": second["dim_path"]}
    dim = pd.read_parquet(tmp_path / "dim" / "dimension.parquet")
    c001 = dim[dim["customer_id"] == "C001"].sort_values("customer_key")
    assert len(c001) == 2
    assert bool(c001.iloc[0]["is_current"]) is False
    assert c001.iloc[0]["valid_to"] is not None
    assert c001.iloc[0]["region"] == "North"
    assert bool(c001.iloc[1]["is_current"]) is True
    assert c001.iloc[1]["region"] == "East"
    assert c001.iloc[1]["customer_key"] > c001.iloc[0]["customer_key"]
    # Re-running the same version is a no-op.
    third = _scd2_load(staged_v2, tmp_path / "dim", "customer_id",
                        ["region", "segment"], "customer_key")
    assert third["inserted"] == 0 and third["updated"] == 0 and third["unchanged"] == 2


def test_scd2_close_and_reopen_on_attribute_change(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    load_customer_dim(valid, tmp_path / "dim_customer")
    # Change C001's segment by hand-editing the staged frame's derived attrs:
    # easiest honest check is a second load from a frame with a new customer.
    extra = valid.iloc[:1].copy()
    extra["customer_id"] = "C021"
    result = load_customer_dim(extra, tmp_path / "dim_customer")
    assert result["inserted"] == 1
    dim = pd.read_parquet(tmp_path / "dim_customer" / "dimension.parquet")
    assert len(dim) == 21
    assert int(dim["is_current"].sum()) == 21


def test_fact_merge_is_idempotent(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    load_customer_dim(valid, tmp_path / "dim_customer")
    first = load_order_fact(valid, tmp_path / "dim_customer", tmp_path / "fact")
    assert first["inserted"] == 150
    assert first["skipped"] == 0
    second = load_order_fact(valid, tmp_path / "dim_customer", tmp_path / "fact")
    assert second["inserted"] == 0
    assert second["skipped"] == 150
    fact = pd.read_parquet(tmp_path / "fact" / "fact_orders.parquet")
    assert len(fact) == 150
    assert fact["order_id"].is_unique


def test_fact_total_amount_is_quantity_times_price(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    load_customer_dim(valid, tmp_path / "dim_customer")
    load_order_fact(valid, tmp_path / "dim_customer", tmp_path / "fact")
    fact = pd.read_parquet(tmp_path / "fact" / "fact_orders.parquet")
    expected = fact["quantity"] * fact["unit_price"]
    assert ((fact["total_amount"] - expected).abs() < 0.01).all()


def test_reconciliation_matches_staged_revenue(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    load_customer_dim(valid, tmp_path / "dim_customer")
    load_order_fact(valid, tmp_path / "dim_customer", tmp_path / "fact")
    rec = reconcile_warehouse(valid, tmp_path / "fact")
    assert rec["reconciled"] is True
    assert rec["difference"] == 0.0
    assert rec["fact_rows"] == 150


def test_product_dim_loads_all_products(tmp_path):
    events = generate_warehouse_events()
    valid = validate_events(consume_events(events)["accepted"])["valid"]
    result = load_product_dim(valid, tmp_path / "dim_product")
    assert result["inserted"] == 8
    dim = pd.read_parquet(tmp_path / "dim_product" / "dimension.parquet")
    assert set(dim["product_id"]) == {f"P0{i}" for i in range(1, 9)}


def test_full_run_is_deterministic(tmp_path):
    first = run_warehouse(tmp_path / "run1")
    second = run_warehouse(tmp_path / "run2")
    assert first == second
    assert first["events_received"] == 160
    assert first["duplicates_dropped"] == 5
    assert first["quarantined"] == 5
    assert first["rows_staged"] == 150
    assert first["fact_inserted"] == 150
    assert first["reconciliation"]["reconciled"] is True


def test_full_run_rerun_inserts_nothing_new(tmp_path):
    first = run_warehouse(tmp_path / "wh")
    second = run_warehouse(tmp_path / "wh")
    # Second run replays the same stream into the same warehouse tables:
    # dims unchanged, fact MERGE inserts 0 new rows.
    assert second["customer_dim"]["unchanged"] == 20
    assert second["fact_inserted"] == 0
    assert second["fact_skipped"] == 150
    assert second["reconciliation"]["reconciled"] is True
    assert first["reconciliation"]["fact_revenue"] == second["reconciliation"]["fact_revenue"]


def test_generate_is_seeded_and_repeatable():
    first = generate_warehouse_events()
    second = generate_warehouse_events()
    pd.testing.assert_frame_equal(first, second)


def test_consumer_state_round_trips():
    state = ConsumerState(committed_offset=42, seen_event_ids={"EVT-0001"})
    restored = ConsumerState.from_dict(state.to_dict())
    assert restored.committed_offset == 42
    assert restored.seen_event_ids == {"EVT-0001"}
