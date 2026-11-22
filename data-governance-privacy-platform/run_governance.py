"""End-to-end governance demo.

Seeds a small catalog of synthetic datasets (members, transactions, loan
applications, support tickets), runs classification, evaluates a set of
access requests, enforces retention, processes one erasure request, and
writes ``governance_report.txt`` and ``governance_report.json`` next to
this file.

All data is synthetic and seeded in this file. Nothing here touches a
real Snowflake, S3, or Postgres system — the catalog, tables and access
log all run in memory as a local simulation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from governance.access import AccessEvaluator, AccessRequest  # noqa: E402
from governance.catalog import Catalog, Column, Dataset  # noqa: E402
from governance.classify import classify_dataset  # noqa: E402
from governance.erasure import process_erasure  # noqa: E402
from governance.masking import mask_value  # noqa: E402
from governance.retention import evaluate_catalog  # noqa: E402

ERASURE_SUBJECT = "SUBJ-1007"

# Dataset ages in days (age of the oldest record) for the retention run.
DATASET_AGES = {
    "members": 400,
    "transactions": 800,
    "loan_applications": 900,
    "support_tickets": 100,
}

ACCESS_REQUESTS = [
    AccessRequest("analyst", "reporting", "members", ["member_id", "full_name"]),
    AccessRequest("analyst", "reporting", "members", ["ssn"]),
    AccessRequest("auditor", "audit", "transactions", ["amount", "merchant"]),
    AccessRequest("data-engineer", "model-training", "loan_applications", ["credit_score"]),
    AccessRequest("admin", "operations", "members", ["ssn"]),
    AccessRequest("data-engineer", "support", "transactions", ["account_number"]),
    AccessRequest("analyst", "model-training", "transactions", ["amount"]),
    AccessRequest("intern", "reporting", "members", ["member_id"]),
]


def seed_catalog() -> Catalog:
    """Build the synthetic catalog. Every person/record below is invented."""
    catalog = Catalog()

    catalog.register(Dataset(
        name="members", owner_team="member-platform", system="Snowflake",
        retention_days=730, legal_hold=False,
        columns=[
            Column("subject_id", "string"), Column("member_id", "string"),
            Column("full_name", "string"), Column("email", "string"),
            Column("phone", "string"), Column("date_of_birth", "date"),
            Column("ssn", "string"), Column("account_number", "string"),
            Column("state", "string"), Column("signup_channel", "string"),
        ],
        rows=[
            {"subject_id": "SUBJ-1001", "member_id": "M-1001", "full_name": "Alex Rivera",
             "email": "alex.rivera@example.com", "phone": "+1-415-555-0132",
             "date_of_birth": "1990-04-12", "ssn": "123-45-6789",
             "account_number": "1000000001234567", "state": "CA", "signup_channel": "mobile"},
            {"subject_id": "SUBJ-1007", "member_id": "M-1007", "full_name": "Jordan Lee",
             "email": "jordan.lee@example.com", "phone": "+1-212-555-0148",
             "date_of_birth": "1988-11-03", "ssn": "987-65-4321",
             "account_number": "1000000007654321", "state": "NY", "signup_channel": "web"},
            {"subject_id": "SUBJ-1003", "member_id": "M-1003", "full_name": "Priya Nair",
             "email": "priya.nair@example.com", "phone": "+1-312-555-0176",
             "date_of_birth": "1995-07-21", "ssn": "456-78-9012",
             "account_number": "1000000003456789", "state": "IL", "signup_channel": "mobile"},
        ],
    ))

    catalog.register(Dataset(
        name="transactions", owner_team="payments", system="Snowflake",
        retention_days=730, legal_hold=False,
        columns=[
            Column("subject_id", "string"), Column("transaction_id", "string"),
            Column("account_number", "string"), Column("amount", "decimal"),
            Column("merchant", "string"), Column("transaction_date", "date"),
        ],
        rows=[
            {"subject_id": "SUBJ-1001", "transaction_id": "T-9001",
             "account_number": "1000000001234567", "amount": 42.50,
             "merchant": "Corner Grocers", "transaction_date": "2026-10-02"},
            {"subject_id": "SUBJ-1007", "transaction_id": "T-9002",
             "account_number": "1000000007654321", "amount": 129.99,
             "merchant": "Northwind Books", "transaction_date": "2026-10-05"},
            {"subject_id": "SUBJ-1007", "transaction_id": "T-9003",
             "account_number": "1000000007654321", "amount": 18.75,
             "merchant": "City Transit", "transaction_date": "2026-10-09"},
            {"subject_id": "SUBJ-1003", "transaction_id": "T-9004",
             "account_number": "1000000003456789", "amount": 250.00,
             "merchant": "Harbor Outfitters", "transaction_date": "2026-10-11"},
        ],
    ))

    catalog.register(Dataset(
        name="loan_applications", owner_team="lending", system="Postgres",
        retention_days=1095, legal_hold=True,  # under legal hold: no deletion, no model training
        columns=[
            Column("subject_id", "string"), Column("application_id", "string"),
            Column("full_name", "string"), Column("ssn", "string"),
            Column("income", "decimal"), Column("credit_score", "integer"),
            Column("loan_amount", "decimal"), Column("street_address", "string"),
        ],
        rows=[
            {"subject_id": "SUBJ-1007", "application_id": "L-5001", "full_name": "Jordan Lee",
             "ssn": "987-65-4321", "income": 85000, "credit_score": 712,
             "loan_amount": 25000, "street_address": "482 Maple Ave, Buffalo, NY 14201"},
            {"subject_id": "SUBJ-1002", "application_id": "L-5002", "full_name": "Sam Ortiz",
             "ssn": "234-56-7890", "income": 64000, "credit_score": 688,
             "loan_amount": 12000, "street_address": "17 River Rd, Austin, TX 78701"},
        ],
    ))

    catalog.register(Dataset(
        name="support_tickets", owner_team="member-support", system="S3",
        retention_days=365, legal_hold=False,
        columns=[
            Column("subject_id", "string"), Column("ticket_id", "string"),
            Column("email", "string"), Column("issue_category", "string"),
            Column("message", "string"),
        ],
        rows=[
            {"subject_id": "SUBJ-1007", "ticket_id": "S-3001",
             "email": "jordan.lee@example.com", "issue_category": "login",
             "message": "Cannot reset password on mobile app."},
            {"subject_id": "SUBJ-1001", "ticket_id": "S-3002",
             "email": "alex.rivera@example.com", "issue_category": "billing",
             "message": "Question about last statement."},
        ],
    ))
    return catalog


def run_demo() -> dict:
    catalog = seed_catalog()

    # 1. Classification — write the result back onto each column.
    classifications = {}
    for dataset in catalog.all():
        result = classify_dataset(dataset.column_names(), dataset.rows)
        classifications[dataset.name] = result
        for col_name, classification in result.items():
            col = dataset.column(col_name)
            col.sensitivity = classification.sensitivity
            col.classification_rule = classification.rule
    total_columns = sum(len(v) for v in classifications.values())
    by_level: dict = {}
    for result in classifications.values():
        for c in result.values():
            by_level[c.sensitivity] = by_level.get(c.sensitivity, 0) + 1

    # 2. Access evaluation (least privilege, purpose-based).
    evaluator = AccessEvaluator(catalog)
    decisions = [evaluator.evaluate(req) for req in ACCESS_REQUESTS]
    allowed = sum(1 for d in decisions if d.allowed)
    denied = len(decisions) - allowed

    # 3. Masking sample: how an analyst sees one member row vs an admin.
    member_row = catalog.get("members").rows[0]
    masking_sample = {}
    for role in ("analyst", "admin"):
        masking_sample[role] = {
            col.name: mask_value(member_row[col.name], col.sensitivity or "internal", role)
            for col in catalog.get("members").columns
        }

    # 4. Retention enforcement.
    retention = evaluate_catalog(catalog, DATASET_AGES)
    retention_counts = {}
    for action in retention:
        retention_counts[action.action] = retention_counts.get(action.action, 0) + 1

    # 5. CCPA/GDPR erasure for one subject.
    erasure = process_erasure(catalog, ERASURE_SUBJECT)

    report = {
        "datasets": len(catalog),
        "columns_classified": total_columns,
        "classification_by_level": by_level,
        "classifications": {
            ds: {col: {"sensitivity": c.sensitivity, "rule": c.rule}
                 for col, c in result.items()}
            for ds, result in classifications.items()
        },
        "access_requests": {
            "total": len(ACCESS_REQUESTS),
            "allowed": allowed,
            "denied": denied,
            "decisions": [
                {"role": req.role, "purpose": req.purpose, "dataset": req.dataset,
                 "columns": req.columns, "allowed": d.allowed, "reason": d.reason,
                 "masked": d.masked}
                for req, d in zip(ACCESS_REQUESTS, decisions)
            ],
        },
        "masking_sample_member_row": masking_sample,
        "retention": {
            "actions": retention_counts,
            "per_dataset": [
                {"dataset": a.dataset, "age_days": a.age_days,
                 "retention_days": a.retention_days, "legal_hold": a.legal_hold,
                 "action": a.action, "reason": a.reason}
                for a in retention
            ],
        },
        "erasure": erasure.as_dict(),
    }
    return report


def render_text_report(report: dict) -> str:
    lines = ["DATA GOVERNANCE & PRIVACY PLATFORM — GOVERNANCE REPORT",
            "All data in this report is synthetic and seeded for demonstration.",
            "",
            f"Datasets registered: {report['datasets']}",
            f"Columns classified: {report['columns_classified']}",
            "Classification by level: " + ", ".join(
                f"{level}={n}" for level, n in sorted(report["classification_by_level"].items())),
            "",
            "CLASSIFICATIONS"]
    for ds, cols in report["classifications"].items():
        lines.append(f"  {ds}:")
        for col, c in cols.items():
            lines.append(f"    {col}: {c['sensitivity']} ({c['rule']})")
    lines += ["",
              "ACCESS REQUESTS",
              f"  total={report['access_requests']['total']} "
              f"allowed={report['access_requests']['allowed']} "
              f"denied={report['access_requests']['denied']}"]
    for d in report["access_requests"]["decisions"]:
        verdict = "ALLOW" if d["allowed"] else "DENY"
        masked = " [masked]" if d["masked"] else ""
        lines.append(f"  [{verdict}]{masked} {d['role']} / {d['purpose']} / "
                     f"{d['dataset']} / {','.join(d['columns'])} — {d['reason']}")
    lines += ["",
              "MASKING SAMPLE (one members row, as each role sees it)"]
    for role, row in report["masking_sample_member_row"].items():
        lines.append(f"  {role}: " + ", ".join(f"{k}={v}" for k, v in row.items()))
    lines += ["",
              "RETENTION",
              "  actions: " + ", ".join(
                  f"{a}={n}" for a, n in sorted(report["retention"]["actions"].items()))]
    for a in report["retention"]["per_dataset"]:
        lines.append(f"  {a['dataset']}: {a['action']} — {a['reason']}")
    lines += ["",
              "ERASURE (CCPA/GDPR)",
              f"  subject: {report['erasure']['subject_id']}",
              f"  records erased: {report['erasure']['erased_total']}",
              f"  held datasets: {report['erasure']['held_datasets'] or 'none'}"]
    for e in report["erasure"]["entries"]:
        lines.append(f"  {e['dataset']}: {e['outcome']} — {e['detail']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    root = Path(__file__).resolve().parent
    report = run_demo()
    (root / "governance_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    (root / "governance_report.txt").write_text(render_text_report(report))

    print("Governance demo complete.")
    print(f"  datasets: {report['datasets']}")
    print(f"  columns classified: {report['columns_classified']} "
          f"({report['classification_by_level']})")
    print(f"  access requests: {report['access_requests']['total']} "
          f"allowed={report['access_requests']['allowed']} "
          f"denied={report['access_requests']['denied']}")
    print(f"  retention actions: {report['retention']['actions']}")
    print(f"  erasure for {report['erasure']['subject_id']}: "
          f"{report['erasure']['erased_total']} record(s) erased, "
          f"held in {report['erasure']['held_datasets'] or 'none'}")
    print("  reports written: governance_report.txt, governance_report.json")


if __name__ == "__main__":
    main()
