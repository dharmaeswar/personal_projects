"""Tests for the catalog-quality module: normalization, defect checks,
the self-learning feedback loop, and the evaluation guardrail."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_quality.catalog import (
    FeedbackLoop,
    check_attribute_consistency,
    check_catalog_completeness,
    check_duplicate_listings,
    evaluate_corrections,
    normalize_brand,
    normalize_price,
    normalize_product,
    normalize_title,
    normalize_weight,
    run_catalog_checks,
)
from eval_quality.catalog_samples import (
    CORRECTION_LABELS,
    CUSTOMER_SIGNALS,
    FEEDBACK_EVENTS,
    PROPOSED_CORRECTIONS,
    build_catalog,
)


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  Nike   Air   Zoom ") == "Nike Air Zoom"


def test_normalize_brand_uses_alias_map():
    assert normalize_brand("nike inc.") == "Nike"
    assert normalize_brand("NIKE") == "Nike"
    assert normalize_brand("apple inc") == "Apple"
    assert normalize_brand("levi strauss") == "Levi's"


def test_normalize_brand_falls_back_to_title_case():
    assert normalize_brand("puma") == "Puma"


def test_normalize_price_variants():
    assert normalize_price(12.99) == (12.99, "USD")
    assert normalize_price("$12.99") == (12.99, "USD")
    assert normalize_price("1,299.99 USD") == (1299.99, "USD")
    assert normalize_price("8.49 EUR") == (8.49, "EUR")


def test_normalize_price_unparseable_returns_none():
    assert normalize_price("call for price") == (None, None)
    assert normalize_price("") == (None, None)


def test_normalize_weight_conversions():
    assert normalize_weight("340 g") == 340.0
    assert normalize_weight("1.5 kg") == 1500.0
    assert normalize_weight("12 oz") == 340.19
    assert normalize_weight("2 lb") == 907.18


def test_normalize_weight_unparseable_returns_none():
    assert normalize_weight("12 stones") is None


def test_normalize_product_adds_normalized_fields():
    prod = normalize_product({
        "id": "X", "title": "  nike  shoe ", "brand": "nike inc.",
        "price": "$59.99", "attributes": {"Weight": "12 oz", "Size": "10"},
    })
    assert prod["title_norm"] == "Nike Shoe"
    assert prod["brand_norm"] == "Nike"
    assert prod["price_amount"] == 59.99
    assert prod["weight_g"] == 340.19
    assert prod["attributes"] == {"weight": "12 oz", "size": "10"}


def test_completeness_flags_missing_brand_and_price():
    findings = check_catalog_completeness([
        {"id": "A", "title": "Bottle", "brand": "", "category": "home",
         "price": 9.99, "attributes": {"material": "steel"}},
        {"id": "B", "title": "Mouse", "brand": "Logi", "category": "home",
         "price": "", "attributes": {"material": "plastic"}},
    ])
    assert any(f["record_id"] == "A" and "brand" in f["detail"]
               for f in findings)
    assert any(f["record_id"] == "B" and "price" in f["detail"]
               for f in findings)


def test_completeness_flags_missing_required_attribute():
    findings = check_catalog_completeness([
        {"id": "A", "title": "Jeans", "brand": "Levi's",
         "category": "apparel", "price": 59.99,
         "attributes": {"color": "blue"}},
    ])
    assert any(f["record_id"] == "A" and "size" in f["detail"]
               for f in findings)


def test_consistency_flags_zero_price_and_unparseable_price():
    findings = check_attribute_consistency([
        {"id": "A", "title": "Mouse", "brand": "Logi",
         "category": "electronics", "price": 0.0,
         "attributes": {"model": "M1"}},
        {"id": "B", "title": "Speaker", "brand": "JBL",
         "category": "electronics", "price": "call for price",
         "attributes": {"model": "F6"}},
    ])
    assert any(f["record_id"] == "A" and f["severity"] == "critical"
               for f in findings)
    assert any(f["record_id"] == "B" and "cannot be parsed" in f["detail"]
               for f in findings)


def test_consistency_flags_price_outlier_against_median():
    products = [
        {"id": "P%d" % i, "title": "Sock", "brand": "Hanes",
         "category": "apparel", "price": 9.99,
         "attributes": {"size": "M", "color": "white"}}
        for i in range(5)
    ]
    products.append({"id": "P9", "title": "Sock", "brand": "Hanes",
                     "category": "apparel", "price": 999.99,
                     "attributes": {"size": "M", "color": "white"}})
    findings = check_attribute_consistency(products)
    assert any(f["record_id"] == "P9" and "5x" in f["detail"]
               for f in findings)


def test_consistency_flags_title_brand_mismatch():
    findings = check_attribute_consistency([
        {"id": "A", "title": "Nike Air Max Shoes", "brand": "Adidas",
         "category": "apparel", "price": 99.99,
         "attributes": {"size": "9", "color": "black"}},
    ])
    assert any("title names" in f["detail"] for f in findings)


def test_duplicate_listings_match_on_normalized_fields():
    findings = check_duplicate_listings([
        {"id": "A", "title": "  Nike   Air Zoom ", "brand": "nike inc.",
         "category": "apparel", "price": 89.99,
         "attributes": {"size": "10", "color": "white"}},
        {"id": "B", "title": "Nike Air Zoom", "brand": "NIKE",
         "category": "apparel", "price": 89.99,
         "attributes": {"size": "10", "color": "white"}},
        {"id": "C", "title": "Nike Air Zoom", "brand": "NIKE",
         "category": "apparel", "price": 89.99,
         "attributes": {"size": "11", "color": "white"}},
    ])
    assert [f["record_id"] for f in findings] == ["A"]
    assert "B" in findings[0]["detail"]


def test_feedback_loop_weight_uses_smoothing():
    loop = FeedbackLoop()
    for _ in range(9):
        loop.ingest_feedback("brand-alias", True)
    loop.ingest_feedback("brand-alias", False)
    # (9 + 1) / (10 + 2) = 0.833
    assert loop.weight("brand-alias") == 0.833


def test_feedback_loop_trusted_rule_may_auto_correct():
    loop = FeedbackLoop()
    for rule, accepted in FEEDBACK_EVENTS:
        loop.ingest_feedback(rule, accepted)
    assert loop.should_auto_correct("brand-alias") is True
    assert loop.should_auto_correct("price-outlier-flag") is False
    assert loop.should_auto_correct("unit-standardize") is True


def test_feedback_loop_needs_minimum_observations():
    loop = FeedbackLoop()
    loop.ingest_feedback("new-rule", True)
    loop.ingest_feedback("new-rule", True)
    assert loop.should_auto_correct("new-rule") is False


def test_feedback_loop_blocks_untrusted_corrections():
    loop = FeedbackLoop()
    for rule, accepted in FEEDBACK_EVENTS:
        loop.ingest_feedback(rule, accepted)
    products = [{"id": "CAT-006", "price": 1299.99},
                {"id": "CAT-011", "brand": "nike inc"}]
    updated, applied, blocked = loop.apply_corrections(
        products, PROPOSED_CORRECTIONS)
    assert updated[1]["brand"] == "Nike"
    assert updated[0]["price"] == 1299.99  # blocked, unchanged
    assert len(applied) == 8
    assert len(blocked) == 2
    assert all(b["rule_id"] == "price-outlier-flag" for b in blocked)


def test_customer_signals_flag_repeat_reports():
    loop = FeedbackLoop()
    for record_id, signal_type in CUSTOMER_SIGNALS:
        loop.ingest_signal(record_id, signal_type)
    assert loop.flagged_records() == ["CAT-005", "CAT-007"]


def test_evaluate_corrections_precision_recall_and_gate():
    proposed = [("A", "brand", "Nike"), ("B", "brand", "Apple"),
                ("C", "brand", "Puma")]
    labels = {("A", "brand"): "Nike", ("B", "brand"): "Apple",
              ("C", "brand"): "Adidas"}
    result = evaluate_corrections(proposed, labels)
    assert result["precision"] == 0.667
    assert result["recall"] == 0.667
    assert result["gate"] == "FAIL"


def test_evaluate_corrections_passes_at_threshold():
    proposed = [(c["record_id"], c["field"], c["new_value"])
                for c in PROPOSED_CORRECTIONS]
    result = evaluate_corrections(proposed, CORRECTION_LABELS)
    assert result["precision"] == 0.9
    assert result["recall"] == 0.9
    assert result["gate"] == "PASS"


def test_sample_catalog_finds_the_planted_defects():
    report = run_catalog_checks(build_catalog())
    assert report["summary"]["total_products"] == 18
    assert report["summary"]["total_findings"] == 9
    assert report["summary"]["critical"] == 7
    assert report["summary"]["warnings"] == 2
    assert report["summary"]["gate"] == "FAIL"
    by_check = report["summary"]["findings_by_check"]
    assert by_check["catalog-completeness"] == 3
    assert by_check["attribute-consistency"] == 5
    assert by_check["duplicate-listing"] == 1
