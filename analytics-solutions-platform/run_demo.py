"""End-to-end demo: ingest -> cleanse/feature-engineer -> dimensional model
-> governed metrics -> PII-governed publish of a dashboard-ready dataset.

All data is synthetic and seeded in code. Nothing here describes a real
company, customer, or policy.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics_solutions.sources import CsvSource, JsonLinesSource, PagedApiSource, write_raw_zone
from analytics_solutions.cleanse import (cleanse_policy_rows, dedupe_by_key,
                                          engineer_activity_features, engineer_policy_features)
from analytics_solutions.models import (build_dim_advisor, build_dim_date,
                                         build_dim_holder, build_fact_policy_activity)
from analytics_solutions.metrics import MetricRegistry, compute_metrics
from analytics_solutions.governance import AccessPolicy, classify_column
from analytics_solutions.quality import run_quality_gate
from analytics_solutions.publish import publish_dataset

AS_OF = date(2026, 11, 20)

POLICY_CSV = """policy_id,holder_id,advisor_id,product,premium_annual,effective_date,status
POL-001,H-101,A-01,term_life,2400,2021-03-15,active
POL-002,H-102,A-01,whole_life,7200,2019-07-01,active
POL-003,H-103,A-02,term_life,950,2023-01-10,active
POL-004,H-104,A-02,disability,3600,2020-11-20,lapsed
POL-005,H-105,A-03,term_life,1800,2022-05-05,active
POL-006,H-106,A-03,whole_life,15000,2018-02-28,active
POL-007,H-107,A-01,term_life,,2022-09-01,active
POL-008,H-108,A-02,term_life,4200,not-a-date,active
"""

ACTIVITY_JSONL = """{"holder_id": "H-101", "activity_date": "2026-11-18", "activity_type": "portal_login"}
{"holder_id": "H-101", "activity_date": "2026-11-05", "activity_type": "payment"}
{"holder_id": "H-102", "activity_date": "2026-11-19", "activity_type": "beneficiary_update"}
{"holder_id": "H-103", "activity_date": "2026-10-02", "activity_type": "portal_login"}
{"holder_id": "H-105", "activity_date": "2026-11-15", "activity_type": "payment"}
{"holder_id": "H-106", "activity_date": "2026-11-20", "activity_type": "claim_status"}
"""

HOLDERS = [
    {"holder_id": "H-101", "holder_name": "Alex Morgan", "state": "WI", "segment": "core"},
    {"holder_id": "H-102", "holder_name": "Sam Rivera", "state": "WI", "segment": "core"},
    {"holder_id": "H-103", "holder_name": "Jo Patel", "state": "IL", "segment": "growth"},
    {"holder_id": "H-104", "holder_name": "Casey Lee", "state": "MN", "segment": "core"},
    {"holder_id": "H-105", "holder_name": "Robin Diaz", "state": "WI", "segment": "growth"},
    {"holder_id": "H-106", "holder_name": "Taylor Brooks", "state": "MI", "segment": "core"},
    {"holder_id": "H-107", "holder_name": "Jamie Fox", "state": "WI", "segment": "core"},
    {"holder_id": "H-108", "holder_name": "Avery Chen", "state": "OH", "segment": "growth"},
]

ADVISOR_PAGES = [
    [{"advisor_id": "A-01", "advisor_name": "Nora Fields", "office": "Milwaukee"},
     {"advisor_id": "A-02", "advisor_name": "Omar Haddad", "office": "Milwaukee"}],
    [{"advisor_id": "A-03", "advisor_name": "Priya Nair", "office": "Madison"}],
]


def main() -> dict:
    out_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    lake_root = os.path.join(out_root, "lake")

    # 1. Ingest from three sources.
    policies_raw = CsvSource("policy_extract", "2.1").read(POLICY_CSV)
    activity_raw = JsonLinesSource("activity_feed", "1.4").read(ACTIVITY_JSONL)
    advisors_raw = PagedApiSource("advisor_api", ADVISOR_PAGES, "1.0", fail_page_once=0).read()
    all_rows = policies_raw + activity_raw + advisors_raw
    raw_files = write_raw_zone(all_rows, lake_root, AS_OF)

    # 2. Cleanse + feature-engineer.
    clean, quarantined = cleanse_policy_rows([r.data for r in policies_raw])
    clean, dupes = dedupe_by_key(clean, "policy_id")
    features = engineer_policy_features(clean, AS_OF)
    activity_feats = engineer_activity_features([r.data for r in activity_raw], AS_OF)

    # 3. Dimensional model.
    _, holder_keys = build_dim_holder(HOLDERS)
    _, advisor_keys = build_dim_advisor([r.data for r in advisors_raw])
    dim_dates = build_dim_date(date(2026, 11, 1), AS_OF)
    facts = build_fact_policy_activity(features, activity_feats, holder_keys, advisor_keys, AS_OF)

    # 4. Governed metrics (single source of truth).
    registry = MetricRegistry()
    registry.register("active_policies", "Count of policies in active status",
                      "count_active_policies", "analytics-eng", "policy", ["fact_policy_activity"])
    registry.register("active_premium_total", "Total annual premium of active policies",
                      "total_premium_active", "analytics-eng", "policy", ["fact_policy_activity"])
    registry.register("active_premium_avg", "Mean annual premium of active policies",
                      "avg_premium_active", "analytics-eng", "policy", ["fact_policy_activity"])
    registry.register("active_policy_share", "Share of policies in active status",
                      "active_policy_share", "analytics-eng", "policy", ["fact_policy_activity"])
    registry.register("avg_activity_30d", "Mean 30-day activity count over active policies",
                      "avg_activity_30d", "analytics-eng", "policy", ["fact_policy_activity"])
    metric_values = compute_metrics(registry, facts)
    metric_versions = {name: "v1" for name in registry.names()}

    # 5. PII governance: classify + project the fact rows for an analyst.
    classes = {c: classify_column(c) for c in ["holder_id", "policy_id", "product", "premium_annual"]}
    policy = AccessPolicy(classes)
    analyst_rows = [policy.project_row(f, "analyst") for f in facts]

    # 6. Quality gate, then publish the dashboard-ready dataset.
    gate = run_quality_gate(
        facts, required=["policy_id", "holder_key", "advisor_key", "premium_annual"],
        unique_key="policy_id", range_checks=[("premium_annual", 0, 1_000_000)],
        facts=facts, dim_keys={"holder": set(holder_keys.values()), "advisor": set(advisor_keys.values())},
        fk_map={"holder_key": "holder", "advisor_key": "advisor"},
        as_of=AS_OF, max_data_date=AS_OF, sla_days=1)
    manifest = publish_dataset(
        analyst_rows, "policy_activity_dashboard", os.path.join(out_root, "publish"),
        AS_OF, schema=sorted(analyst_rows[0].keys()) if analyst_rows else [],
        gate_passed=gate.passed, metric_versions=metric_versions)

    summary = {
        "ingested_rows": len(all_rows),
        "raw_partitions_written": len(raw_files),
        "policies_clean": len(clean),
        "policies_quarantined": len(quarantined),
        "policies_duplicated": len(dupes),
        "fact_rows": len(facts),
        "dim_date_rows": len(dim_dates),
        "metrics": metric_values,
        "quality_gate_passed": gate.passed,
        "quality_failures": [c.detail for c in gate.failures()],
        "published_dataset": manifest["dataset"],
        "published_rows": manifest["row_count"],
        "published_partition": manifest["partition"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    main()
