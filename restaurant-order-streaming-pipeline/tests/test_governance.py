from order_stream.events import seed_events
from order_stream.governance import CATALOG, check_access, check_master_data, check_sla
from order_stream.quality import cleanse
from order_stream.warehouse import fact_rows


def test_catalog_covers_every_dataset():
    names = {d["dataset"] for d in CATALOG}
    assert {"fact_orders", "dim_restaurant", "dim_menu_item", "order_quarantine"} <= names
    assert all(d["owner"] and d["retention_days"] > 0 for d in CATALOG)


def test_master_data_check_passes_for_clean_facts():
    fact = fact_rows(cleanse(seed_events()).clean)
    assert check_master_data(fact) is True


def test_master_data_check_fails_for_unknown_restaurant():
    import pandas as pd

    fact = fact_rows(cleanse(seed_events()).clean)
    fact.loc[0, "restaurant_id"] = "R9999"
    assert check_master_data(fact) is False


def test_sla_flags_low_completeness():
    sla = check_sla(clean=80, quarantined=15, late=5, total=100)
    assert sla["completeness"] == 0.8
    assert sla["sla_met"] is False


def test_sla_passes_for_clean_run():
    sla = check_sla(clean=120, quarantined=3, late=0, total=123)
    assert sla["sla_met"] is True


def test_access_least_privilege():
    assert check_access("data-engineer", "order_quarantine") is True
    assert check_access("analyst", "order_quarantine") is False
    assert check_access("analyst", "fact_orders") is True
    assert check_access("analyst", "no-such-dataset") is False
