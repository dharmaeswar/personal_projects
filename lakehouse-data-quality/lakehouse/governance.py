"""Governed access, point-in-time history and reconciliation for the gold layer.

Mirrors the Databricks lakehouse standards a regulated team applies on top
of a bronze -> silver -> gold pipeline:

- access control: a role may read a table only with a live grant covering
  the requested columns and purpose; every decision is written to an audit
  log, so any read can be traced back to the grant that allowed or denied it.
- point-in-time history: gold revenue can be rebuilt as of any past date,
  so a restated number can be traced to the orders that existed then.
- reconciliation: gold totals must tie back to silver, and the audit log
  must account for every access request (allowed or denied).

All data is synthetic and seeded. Nothing here is a claim about any real
institution, patient, or health record, and no healthcare data is used.
"""

from __future__ import annotations

import pandas as pd

from .data import generate_bronze
from .pipeline import build_gold, build_silver

AS_OF = pd.Timestamp("2026-11-24")
PIT_DATE = pd.Timestamp("2026-06-30")

GOLD_COLUMNS = ["order_date", "category", "region", "order_count", "total_revenue"]
CUSTOMER_COLUMNS = ["customer_id", "customer_name", "region", "signup_date"]


def generate_grants() -> pd.DataFrame:
    """Seeded access grants: role -> table, columns, purpose, validity window.

    Five grants, one of them expired on 2026-10-31 so requests against it
    must be denied even though the role and table otherwise match.
    """
    return pd.DataFrame(
        [
            {
                "grant_id": "G01",
                "role": "analyst_reporting",
                "table": "daily_revenue",
                "columns": ",".join(GOLD_COLUMNS),
                "purpose": "reporting",
                "valid_from": pd.Timestamp("2026-01-01"),
                "valid_until": pd.Timestamp("2026-12-31"),
            },
            {
                "grant_id": "G02",
                "role": "analyst_finance",
                "table": "daily_revenue",
                "columns": "order_date,category,region,total_revenue",
                "purpose": "reconciliation",
                "valid_from": pd.Timestamp("2026-01-01"),
                "valid_until": pd.Timestamp("2026-12-31"),
            },
            {
                "grant_id": "G03",
                "role": "analyst_finance",
                "table": "dim_customer",
                "columns": "customer_id,region",
                "purpose": "reconciliation",
                "valid_from": pd.Timestamp("2026-01-01"),
                "valid_until": pd.Timestamp("2026-12-31"),
            },
            {
                "grant_id": "G04",
                "role": "engineer_platform",
                "table": "daily_revenue",
                "columns": ",".join(GOLD_COLUMNS),
                "purpose": "monitoring",
                "valid_from": pd.Timestamp("2026-01-01"),
                "valid_until": pd.Timestamp("2026-10-31"),
            },
            {
                "grant_id": "G05",
                "role": "auditor_external",
                "table": "daily_revenue",
                "columns": "order_date,category,region,total_revenue",
                "purpose": "audit",
                "valid_from": pd.Timestamp("2026-01-01"),
                "valid_until": pd.Timestamp("2026-12-31"),
            },
        ]
    )


def generate_access_requests() -> pd.DataFrame:
    """Seeded access requests: 8 rows covering allow + each deny reason."""
    return pd.DataFrame(
        [
            {
                "request_id": "R01",
                "role": "analyst_reporting",
                "table": "daily_revenue",
                "columns": ",".join(GOLD_COLUMNS),
                "purpose": "reporting",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R02",
                "role": "analyst_finance",
                "table": "daily_revenue",
                "columns": "order_date,category,region,total_revenue",
                "purpose": "reconciliation",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R03",
                "role": "analyst_finance",
                "table": "dim_customer",
                "columns": "customer_id,region",
                "purpose": "reconciliation",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R04",
                "role": "auditor_external",
                "table": "fact_orders",
                "columns": "order_id,total_amount",
                "purpose": "audit",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R05",
                "role": "analyst_finance",
                "table": "dim_customer",
                "columns": "customer_id,customer_name,region",
                "purpose": "reconciliation",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R06",
                "role": "engineer_platform",
                "table": "daily_revenue",
                "columns": ",".join(GOLD_COLUMNS),
                "purpose": "monitoring",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R07",
                "role": "analyst_reporting",
                "table": "daily_revenue",
                "columns": "order_date,category,region,total_revenue",
                "purpose": "marketing",
                "request_date": pd.Timestamp("2026-11-24"),
            },
            {
                "request_id": "R08",
                "role": "auditor_external",
                "table": "daily_revenue",
                "columns": "order_date,category,region,total_revenue",
                "purpose": "audit",
                "request_date": pd.Timestamp("2026-11-24"),
            },
        ]
    )


def _split(columns: str) -> set[str]:
    return {c.strip() for c in columns.split(",") if c.strip()}


def decide_access(
    grants: pd.DataFrame, requests: pd.DataFrame, as_of: pd.Timestamp = AS_OF
) -> tuple[pd.DataFrame, list[dict]]:
    """Decide every access request against the grants live on ``as_of``.

    Returns (decisions, audit_log). Each decision is allowed only when a
    grant exists for the role + table, is live on ``as_of``, covers the
    requested purpose, and covers every requested column. Denials name the
    first failing reason, in the order: no grant, expired grant, purpose,
    columns. The audit log records one entry per request either way.
    """
    decisions = []
    audit_log = []
    for req in requests.to_dict("records"):
        role, table = req["role"], req["table"]
        wanted = _split(req["columns"])
        same = grants[(grants["role"] == role) & (grants["table"] == table)]
        if same.empty:
            decision, reason, grant_id = "denied", "no grant for role and table", None
        else:
            live = same[
                (same["valid_from"] <= as_of) & (same["valid_until"] >= as_of)
            ]
            if live.empty:
                decision = "denied"
                reason = "grant expired"
                grant_id = str(same.iloc[0]["grant_id"])
            else:
                grant = live.iloc[0]
                grant_id = str(grant["grant_id"])
                if grant["purpose"] != req["purpose"]:
                    decision, reason = "denied", "purpose not covered by grant"
                elif not wanted <= _split(str(grant["columns"])):
                    missing = sorted(wanted - _split(str(grant["columns"])))
                    decision = "denied"
                    reason = f"column not covered by grant: {', '.join(missing)}"
                else:
                    decision, reason = "allowed", "grant covers role, table, columns and purpose"
        decisions.append({**req, "decision": decision, "reason": reason, "grant_id": grant_id})
        audit_log.append(
            {
                "request_id": req["request_id"],
                "role": role,
                "table": table,
                "decision": decision,
                "reason": reason,
                "grant_id": grant_id,
                "as_of": as_of.isoformat(),
            }
        )
    return pd.DataFrame(decisions), audit_log


def reconcile_gold(gold: pd.DataFrame, silver: pd.DataFrame) -> dict:
    """Gold daily revenue must equal silver revenue to the cent."""
    silver_revenue = round(float(silver["total_amount"].sum()), 2)
    gold_revenue = round(float(gold["total_revenue"].sum()), 2)
    difference = round(gold_revenue - silver_revenue, 2)
    return {
        "silver_revenue": silver_revenue,
        "gold_revenue": gold_revenue,
        "difference": difference,
        "gold_groups": len(gold),
        "silver_rows": len(silver),
        "reconciled": abs(difference) <= 0.01,
    }


def point_in_time_gold(
    silver: pd.DataFrame, products: pd.DataFrame, as_of: pd.Timestamp
) -> pd.DataFrame:
    """Rebuild gold using only silver orders dated on or before ``as_of``."""
    subset = silver[silver["order_date"] <= as_of]
    if subset.empty:
        return build_gold(silver.iloc[0:0], products)
    return build_gold(subset, products)


def run_governance() -> dict:
    """End-to-end governed run: bronze -> silver -> gold, then governance."""
    bronze = generate_bronze()
    silver, quarantine = build_silver(
        bronze["orders"], bronze["customers"], bronze["products"]
    )
    gold = build_gold(silver, bronze["products"])
    grants = generate_grants()
    requests = generate_access_requests()
    decisions, audit_log = decide_access(grants, requests)
    reconciliation = reconcile_gold(gold, silver)
    pit_gold = point_in_time_gold(silver, bronze["products"], PIT_DATE)
    pit_reconciliation = reconcile_gold(
        pit_gold, silver[silver["order_date"] <= PIT_DATE]
    )
    return {
        "bronze_orders": len(bronze["orders"]),
        "silver_rows": len(silver),
        "quarantined_rows": len(quarantine),
        "gold_groups": len(gold),
        "gold_revenue": reconciliation["gold_revenue"],
        "grants": len(grants),
        "requests": len(requests),
        "allowed": int((decisions["decision"] == "allowed").sum()),
        "denied": int((decisions["decision"] == "denied").sum()),
        "audit_entries": len(audit_log),
        "reconciliation": reconciliation,
        "point_in_time_date": PIT_DATE.date().isoformat(),
        "point_in_time_groups": len(pit_gold),
        "point_in_time_revenue": pit_reconciliation["gold_revenue"],
        "point_in_time_reconciled": pit_reconciliation["reconciled"],
        "decisions": decisions,
        "audit_log": audit_log,
    }
