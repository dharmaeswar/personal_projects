import json
import os

import pandas as pd

from order_stream.pipeline import run_pipeline


def test_full_pipeline_end_to_end(tmp_path):
    warehouse = str(tmp_path / "warehouse")
    out = str(tmp_path / "out")
    state, report = run_pipeline(warehouse_dir=warehouse, out_dir=out)
    assert state.produced == 128  # 120 seeded + 3 duplicates + 2 late + 3 bad
    assert state.clean == 120
    assert state.quarantined == 5  # 3 bad rows + 2 late arrivals
    assert state.late == 2
    assert state.errors == []
    assert state.partitions_written > 0
    assert report["master_data_ok"] is True
    assert report["access_violations"] == []
    assert report["topic_lag_after_commit"] == 0

    fact_files = []
    for root, _, files in os.walk(os.path.join(warehouse, "fact_orders")):
        fact_files.extend(os.path.join(root, f) for f in files if f.endswith(".parquet"))
    fact = pd.concat([pd.read_parquet(f) for f in fact_files], ignore_index=True)
    assert len(fact) == 120
    assert abs(fact["total_amount"].sum() - (fact["quantity"] * fact["unit_price"]).sum()) < 0.01

    quarantine = pd.read_parquet(os.path.join(warehouse, "order_quarantine.parquet"))
    assert set(quarantine["reason"]) >= {"non_positive_quantity_or_price", "unknown_menu_code",
                                         "total_amount_mismatch"}

    run_state = json.load(open(os.path.join(out, "run_state.json")))
    assert run_state["clean"] == 120 and run_state["produced"] == 128


def test_pipeline_is_idempotent_on_rerun(tmp_path):
    warehouse = str(tmp_path / "warehouse")
    out = str(tmp_path / "out")
    run_pipeline(warehouse_dir=warehouse, out_dir=out)
    state, _ = run_pipeline(warehouse_dir=warehouse, out_dir=out)
    assert state.clean == 120  # same deterministic seed, same result
