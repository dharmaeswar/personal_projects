"""Tests for the distributor ETL: ingest, rules, warehouse, loads."""

import os
import sqlite3

import pytest

from distributor_etl import ingest, loads, validate, warehouse

DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")


def _ctx():
    inventory = ingest.parse_inventory(
        os.path.join(DATA, "distributor_inventory.json"))
    customers = ingest.parse_customers(
        os.path.join(DATA, "distributor_customers.csv"))
    return {"inventory": inventory, "customers": customers,
            "seen_shipment_ids": set()}


def _good():
    return {"shipment_id": "S100", "customer_id": "C-101",
            "product_id": "P-1001", "quantity": 10,
            "ship_date": "2026-11-02", "amount": 125.00,
            "warehouse_id": "WH-01"}


def test_parse_shipments_and_masters():
    shipments, errors = ingest.parse_shipments(
        os.path.join(DATA, "distributor_shipments.csv"))
    assert len(shipments) == 12 and errors == []
    inventory = ingest.parse_inventory(
        os.path.join(DATA, "distributor_inventory.json"))
    assert inventory["P-1001"]["unit_price"] == 12.50
    customers = ingest.parse_customers(
        os.path.join(DATA, "distributor_customers.csv"))
    assert customers["C-104"]["active"] == "N"


def test_parse_malformed_row_reported_not_crashed(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("shipment_id,customer_id,product_id,quantity,ship_date,"
                   "amount,warehouse_id\n"
                   "S1,C-101,P-1001,ten,2026-11-02,125.00,WH-01\n"
                   "S2,C-101,P-1001,5,2026-11-02,62.50,WH-01\n")
    shipments, errors = ingest.parse_shipments(str(bad))
    assert len(shipments) == 1 and len(errors) == 1


def test_each_rule_catches_its_case():
    ctx = _ctx()
    assert validate.validate_shipment(_good(), ctx) == []
    dup = _good()
    assert "duplicate" in validate.validate_shipment(dup, ctx)[0]
    bad_qty = dict(_good(), shipment_id="S101", quantity=0)
    assert any("not positive" in v
               for v in validate.validate_shipment(bad_qty, ctx))
    bad_prod = dict(_good(), shipment_id="S102", product_id="P-9999")
    assert any("unknown product" in v
               for v in validate.validate_shipment(bad_prod, ctx))
    bad_amt = dict(_good(), shipment_id="S103", amount=1.00)
    assert any("does not match" in v
               for v in validate.validate_shipment(bad_amt, ctx))
    bad_cust = dict(_good(), shipment_id="S104", customer_id="C-104")
    assert any("not active" in v
               for v in validate.validate_shipment(bad_cust, ctx))
    bad_date = dict(_good(), shipment_id="S105", ship_date="2027-01-15")
    assert any("outside reporting window" in v
               for v in validate.validate_shipment(bad_date, ctx))


def test_batch_split_seed_data():
    shipments, _ = ingest.parse_shipments(
        os.path.join(DATA, "distributor_shipments.csv"))
    valid, quarantined = validate.validate_batch(
        shipments, _ctx()["inventory"], _ctx()["customers"])
    assert len(valid) == 6 and len(quarantined) == 6
    reasons = " ".join(v for q in quarantined for v in q["violations"])
    for phrase in ("duplicate", "not positive", "unknown product",
                   "does not match", "not active", "outside reporting"):
        assert phrase in reasons


def test_full_then_incremental_loads(tmp_path):
    db = str(tmp_path / "wh.db")
    inv = os.path.join(DATA, "distributor_inventory.json")
    cust = os.path.join(DATA, "distributor_customers.csv")
    full = loads.run_load(
        db, os.path.join(DATA, "distributor_shipments.csv"),
        inv, cust, mode="full")
    assert full["loaded_rows"] == 6 and loads.reconcile(full)
    assert full["watermark"] == "2026-11-07"
    inc = loads.run_load(
        db, os.path.join(DATA, "distributor_shipments_batch2.csv"),
        inv, cust, mode="incremental")
    assert inc["loaded_rows"] == 2 and loads.reconcile(inc)
    rerun = loads.run_load(
        db, os.path.join(DATA, "distributor_shipments_batch2.csv"),
        inv, cust, mode="incremental")
    assert rerun["loaded_rows"] == 0 and rerun["skipped_rows"] == 2
    assert loads.reconcile(rerun)
    conn = warehouse.connect(db)
    assert warehouse.fact_count(conn) == 8
    totals = dict((name, (qty, amt)) for name, qty, amt
                  in warehouse.total_shipped_by_product(conn))
    assert totals["Metformin 500mg"][0] == 800  # 500 + 300
    conn.close()


def test_dimensional_model_tables_exist(tmp_path):
    db = str(tmp_path / "wh.db")
    conn = warehouse.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"dim_product", "dim_customer", "fact_shipments",
            "load_log"} <= tables
    conn.close()
