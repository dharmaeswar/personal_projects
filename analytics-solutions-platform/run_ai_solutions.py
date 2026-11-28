"""Demo: AI solutions layer for Client Services stakeholder questions.

Runs the agentic solution runner over a small seeded client dataset:
enriches client records from transaction + activity feeds, answers
"which client segment leads 30-day volume and what drives it?" with a
grounded answer, and prints a JSON summary with the reproducibility hash.

All data is synthetic and seeded in code. Nothing here describes a real
company, customer, or client.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics_solutions.ai_solutions import run_solution
from analytics_solutions.discovery import register_product
from analytics_solutions.metrics import MetricRegistry

AS_OF = date(2026, 11, 20)

CLIENTS = [
    {"client_id": "C-1", "segment": "retail", "channel": "portal", "signup_date": "2024-01-10"},
    {"client_id": "C-2", "segment": "retail", "channel": "portal", "signup_date": "2024-02-10"},
    {"client_id": "C-3", "segment": "retail", "channel": "branch", "signup_date": "2024-03-10"},
    {"client_id": "C-4", "segment": "commercial", "channel": "portal", "signup_date": "2023-05-01"},
    {"client_id": "C-5", "segment": "commercial", "channel": "branch", "signup_date": "2023-06-01"},
    {"client_id": "C-6", "segment": "commercial", "channel": "portal", "signup_date": "2023-07-01"},
]

TRANSACTIONS = []
for i, cid in enumerate(["C-1", "C-2", "C-3", "C-4", "C-5", "C-6"]):
    for j in range(i + 1):
        TRANSACTIONS.append({"txn_id": f"T-{cid}-{j}", "client_id": cid,
                             "amount": 100.0 * (i + 1),
                             "txn_date": "2026-11-1%d" % (j % 9)})

ACTIVITY_COUNTS = {"C-1": 1, "C-2": 2, "C-3": 1, "C-4": 3, "C-5": 2, "C-6": 4}
ACTIVITIES = []
for cid, n in ACTIVITY_COUNTS.items():
    for k in range(n):
        ACTIVITIES.append({"client_id": cid, "activity_date": "2026-11-1%d" % (5 + k),
                           "activity_type": "portal_login"})


def main() -> None:
    registry = MetricRegistry()
    registry.register("active_policies", "count of active policies",
                      "count_active_policies", "analytics", "policy",
                      ["fact_policy_activity"])
    facts = [{"is_active": True, "premium_annual": 1000.0, "activity_count_30d": 2}
             for _ in range(3)]
    facts.append({"is_active": False, "premium_annual": 500.0, "activity_count_30d": 0})
    catalog = []
    register_product(catalog, {
        "product_id": "P-1", "name": "Client volume by segment",
        "domain": "client services", "owner": "analytics",
        "description": "30-day transaction volume by client segment",
        "keywords": ["volume", "segment", "client"],
        "source_datasets": ["fact_client_activity"],
        "freshness_sla_hours": 24, "quality_score": 90})
    solution = run_solution(
        "which client segment leads 30-day volume and what drives it?",
        registry=registry, facts=facts, catalog=catalog,
        clients=CLIENTS, transactions=TRANSACTIONS, activities=ACTIVITIES,
        as_of=AS_OF, run_id="demo-2026-11-28", seed=7)
    print(json.dumps({
        "answer": solution["answer"],
        "top_segment": solution["top_segment"],
        "segment_volumes": solution["segment_volumes"],
        "tool_calls": [t["tool"] for t in solution["tool_calls"]],
        "input_hash": solution["input_hash"],
    }, indent=2))


if __name__ == "__main__":
    main()
