from datetime import datetime

import pandas as pd

from order_stream.events import seed_events
from order_stream.quality import cleanse
from order_stream.warehouse import dim_menu_item_scd2, dim_restaurant, fact_rows, write_fact


def test_fact_rows_carry_star_schema_fields():
    clean = cleanse(seed_events()).clean
    fact = fact_rows(clean)
    assert set(fact.columns) >= {
        "order_id", "event_date", "event_time", "restaurant_id",
        "market", "region", "channel", "menu_code", "menu_item",
        "quantity", "unit_price", "total_amount",
    }
    assert fact["total_amount"].sum() == round((fact["quantity"] * fact["unit_price"]).sum(), 2)


def test_write_fact_partitions_by_date_and_restaurant(tmp_path):
    clean = cleanse(seed_events()).clean
    written = write_fact(fact_rows(clean), str(tmp_path))
    assert written
    assert all("event_date=" in p and "restaurant_id=" in p for p in written)
    back = pd.concat([pd.read_parquet(p) for p in written], ignore_index=True)
    assert len(back) == len(clean)


def test_write_fact_writes_nothing_for_empty_input(tmp_path):
    assert write_fact(pd.DataFrame(), str(tmp_path)) == []


def test_dim_restaurant_matches_master_data():
    dim = dim_restaurant()
    assert len(dim) == 5
    assert set(dim["region"]) == {"Midwest", "South"}


def test_scd2_price_change_keeps_history():
    dim = dim_menu_item_scd2([("M001", 6.49, datetime(2026, 11, 21))])
    rows = dim[dim["menu_code"] == "M001"].sort_values("valid_from")
    assert len(rows) == 2
    assert rows.iloc[0]["valid_to"] == "2026-11-21" and not rows.iloc[0]["is_current"]
    assert rows.iloc[1]["unit_price"] == 6.49 and rows.iloc[1]["is_current"]
