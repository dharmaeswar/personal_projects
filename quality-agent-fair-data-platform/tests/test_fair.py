from datetime import datetime, timedelta

import pytest

from quality_platform import seed
from quality_platform.fair import FairRegistry, RegistryError, validate_product


def _product(**overrides):
    base = {
        "product_id": "p-1", "name": "Batch Release", "domain": "quality",
        "owner": "quality-analytics", "description": "release cycle time",
        "keywords": ["batch"], "schema": [{"name": "batch_id", "type": "string"}],
        "freshness_sla_hours": 24, "quality_score": 90,
        "access_level": "internal", "version": "1.0.0", "status": "live",
        "last_updated": datetime(2026, 11, 25, 8, 0),
    }
    base.update(overrides)
    return base


def test_validate_ok():
    assert validate_product(_product()) == []


def test_validate_missing_field():
    p = _product()
    del p["owner"]
    assert any("owner" in e for e in validate_product(p))


def test_validate_bad_quality_score():
    assert validate_product(_product(quality_score=101))
    assert validate_product(_product(quality_score=-1))


def test_validate_bad_access_level():
    assert validate_product(_product(access_level="secret"))


def test_validate_bad_schema():
    assert validate_product(_product(schema=[{"name": "x"}]))


def test_register_and_get():
    reg = FairRegistry()
    reg.register(_product())
    assert reg.get("p-1")["name"] == "Batch Release"


def test_register_duplicate_rejected():
    reg = FairRegistry()
    reg.register(_product())
    with pytest.raises(RegistryError):
        reg.register(_product())


def test_search_ranks_name_match_first():
    reg = seed.build_registry()
    results = reg.search("batch release")
    assert results[0]["product_id"] == "batch-release"


def test_search_excludes_draft():
    reg = FairRegistry()
    reg.register(_product(product_id="draft-1", status="draft"))
    assert reg.search("batch") == []


def test_search_domain_and_quality_filters():
    reg = seed.build_registry()
    # "capa" matches capa-tracker (name) and batch-release (description).
    # min_quality=90 drops capa-tracker (88) but keeps batch-release (94).
    assert [p["product_id"] for p in reg.search("capa", min_quality=90)] == ["batch-release"]
    # No floor: capa-tracker ranks first (name match weighs double).
    assert [p["product_id"] for p in reg.search("capa", min_quality=80)] == [
        "capa-tracker", "batch-release"]


def test_freshness_status():
    reg = seed.build_registry()
    product = reg.get("batch-release")
    assert reg.freshness_status(product, datetime(2026, 11, 25, 12, 0)) == "fresh"
    assert reg.freshness_status(product, datetime(2026, 11, 27, 12, 0)) == "stale"
    assert reg.freshness_status({"freshness_sla_hours": 24}, datetime.now()) == "stale"


def test_check_access_restricted():
    reg = seed.build_registry()
    capa = reg.get("capa-tracker")
    assert reg.check_access(capa, "quality-admin") is True
    assert reg.check_access(capa, "analyst") is False
    assert reg.check_access(reg.get("batch-release"), "external") is False
    assert reg.check_access(reg.get("batch-release"), "analyst") is True


def test_lineage_and_unknown():
    reg = seed.build_registry()
    assert reg.lineage("batch-release")[0]["source"] == "lims-batch-extract"
    with pytest.raises(RegistryError):
        reg.lineage("nope")


def test_product_card():
    reg = seed.build_registry()
    card = reg.product_card(reg.get("deviation-register"))
    assert card["fields"] == ["deviation_id", "batch_id", "category", "severity"]
    assert card["quality_score"] == 91


def test_seed_metrics():
    q2 = seed.batch_metrics("Q2")
    assert q2["mean_release_cycle_days"] == 20.0
    assert q2["batches"] == 6
    q3 = seed.batch_metrics("Q3")
    assert q3["mean_release_cycle_days"] == 27.5
    assert q3["total_deviations"] == 15
    assert seed.batch_metrics("Q9") is None


def test_deviation_breakdown():
    bd = seed.deviation_breakdown("Q3")
    assert bd["total"] == 10
    assert bd["by_category"]["documentation"] == 7
