"""Tests for analytics_solutions.discovery (data-product discovery service)."""

from datetime import datetime, timedelta

import pytest

from analytics_solutions.discovery import (
    CatalogError,
    answer_question,
    freshness_status,
    list_by_domain,
    product_card,
    register_product,
    search_products,
)


def _product(pid="policy_activity", **overrides):
    base = {
        "product_id": pid,
        "name": "Policy Activity Dashboard",
        "domain": "insurance",
        "owner": "analytics-platform",
        "description": "Active policies, premium carried and holder engagement by day.",
        "keywords": ["policy", "premium", "engagement"],
        "source_datasets": ["policy_extract", "activity_feed"],
        "freshness_sla_hours": 24,
        "quality_score": 94,
        "contains_pii": True,
    }
    base.update(overrides)
    return base


def test_register_adds_product_with_defaults():
    catalog = []
    stored = register_product(catalog, _product())
    assert len(catalog) == 1
    assert stored["status"] == "live"
    assert stored["contains_pii"] is True


def test_register_rejects_missing_field():
    catalog = []
    bad = _product()
    del bad["owner"]
    with pytest.raises(CatalogError, match="owner"):
        register_product(catalog, bad)


def test_register_rejects_duplicate_id():
    catalog = []
    register_product(catalog, _product())
    with pytest.raises(CatalogError, match="duplicate"):
        register_product(catalog, _product())


def test_register_rejects_bad_quality_score():
    catalog = []
    with pytest.raises(CatalogError, match="quality_score"):
        register_product(catalog, _product(quality_score=120))


def test_register_rejects_empty_sources():
    catalog = []
    with pytest.raises(CatalogError, match="source_datasets"):
        register_product(catalog, _product(source_datasets=[]))


def test_search_ranks_name_match_first():
    catalog = []
    register_product(catalog, _product())
    register_product(catalog, _product(
        pid="advisor_engagement", name="Advisor Engagement",
        description="Advisor activity and outreach volume.",
        keywords=["advisor"], quality_score=99))
    results = search_products(catalog, "policy premium")
    assert [p["product_id"] for p in results] == ["policy_activity"]


def test_search_hides_deprecated_and_draft():
    catalog = []
    register_product(catalog, _product())
    register_product(catalog, _product(pid="old", name="Old Policy Report",
                                        status="deprecated"))
    register_product(catalog, _product(pid="draft", name="Policy Draft",
                                        status="draft"))
    assert [p["product_id"] for p in search_products(catalog, "policy")] == [
        "policy_activity"]


def test_search_domain_and_quality_filters():
    catalog = []
    register_product(catalog, _product())
    register_product(catalog, _product(pid="sales", name="Sales Pipeline",
                                        domain="sales", quality_score=60))
    assert search_products(catalog, "", domain="sales")[0]["product_id"] == "sales"
    assert search_products(catalog, "", min_quality=90) == [catalog[0]]
    assert search_products(catalog, "", domain="sales", min_quality=90) == []


def test_search_no_match_returns_empty():
    catalog = []
    register_product(catalog, _product())
    assert search_products(catalog, "underwriting catastrophe") == []


def test_freshness_status_fresh_and_stale():
    product = _product()
    now = datetime(2026, 11, 26, 12, 0)
    fresh = freshness_status(product, now - timedelta(hours=5), now)
    assert fresh["status"] == "fresh"
    stale = freshness_status(product, now - timedelta(hours=30), now)
    assert stale["status"] == "stale"
    assert stale["age_hours"] == 30.0


def test_answer_question_picks_best_and_names_terms():
    catalog = []
    register_product(catalog, _product())
    register_product(catalog, _product(pid="advisor", name="Advisor Activity",
                                        description="Advisor outreach volume.",
                                        keywords=["advisor"]))
    answer = answer_question(catalog, "which policies are active and what premium do they carry?")
    assert answer["answer"] == "policy_activity"
    assert "policies" in answer["reason"]
    assert "premium" in answer["reason"]


def test_answer_question_no_match_is_explicit():
    catalog = []
    register_product(catalog, _product())
    answer = answer_question(catalog, "how many rockets launched?")
    assert answer["answer"] is None
    assert answer["alternatives"] == []


def test_list_by_domain_groups_and_orders():
    catalog = []
    register_product(catalog, _product())
    register_product(catalog, _product(pid="claims", name="Claims Overview",
                                        domain="insurance", quality_score=80))
    register_product(catalog, _product(pid="sales", name="Sales Pipeline",
                                        domain="sales", quality_score=60))
    grouped = list_by_domain(catalog)
    assert grouped["insurance"] == ["policy_activity", "claims"]
    assert grouped["sales"] == ["sales"]


def test_product_card_includes_freshness_when_given():
    product = _product()
    now = datetime(2026, 11, 26, 12, 0)
    card = product_card(product, last_refresh=now - timedelta(hours=2), now=now)
    assert card["freshness"] == "fresh"
    assert card["sources"] == ["policy_extract", "activity_feed"]
    assert card["contains_pii"] is True
