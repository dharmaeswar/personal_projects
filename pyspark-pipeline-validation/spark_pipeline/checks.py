"""Data-quality checks run on the cleansed layer and on the gold aggregates."""
import pandas as pd

from .schema import check_schema


def run_quality_checks(cleansed, gold, reconciliation):
    """Return a list of (check, status, detail) rows for the report."""
    results = []

    base = cleansed.drop(
        columns=[c for c in ("product_category", "amount_band", "is_high_value") if c in cleansed.columns]
    )
    schema_problems = check_schema(base)
    results.append(
        ("schema_enforced", "PASS" if not schema_problems else "FAIL",
         "no violations" if not schema_problems else "; ".join(schema_problems))
    )
    results.append(
        ("completeness_user_id", "PASS" if cleansed["user_id"].notna().all() else "FAIL",
         f"nulls={int(cleansed['user_id'].isna().sum())}")
    )
    results.append(
        ("uniqueness_event_id", "PASS" if cleansed["event_id"].is_unique else "FAIL",
         f"duplicates={int(cleansed.duplicated('event_id').sum())}")
    )
    results.append(
        ("amount_non_negative", "PASS" if (cleansed["amount"] >= 0).all() else "FAIL",
         f"negative={int((cleansed['amount'] < 0).sum())}")
    )
    results.append(
        ("amount_arithmetic", "PASS"
         if ((cleansed["amount"] - cleansed["quantity"] * cleansed["unit_price"]).abs() <= 0.01).all()
         else "FAIL",
         "amount == quantity * unit_price within 0.01")
    )
    results.append(
        ("referential_product", "PASS" if cleansed["product_category"].notna().all() else "FAIL",
         f"unknown products={int(cleansed['product_category'].isna().sum())}")
    )
    results.append(
        ("reconciliation_gold_vs_cleansed",
         "PASS" if reconciliation["passed"] else "FAIL",
         f"gold_rows={reconciliation['gold_rows']}, "
         f"max_revenue_diff={reconciliation['max_revenue_diff']}")
    )
    return results
