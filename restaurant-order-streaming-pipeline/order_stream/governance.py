"""Data governance: metadata catalog, master-data standards, SLA checks.

Covers the posting's governance duties: a metadata catalog (dataset
registry with owner, source system, retention, classification), master-data
standards (every restaurant and menu code must exist in master data),
quality SLAs (timeliness, completeness, accuracy), and role-based access.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .events import MENU, RESTAURANTS

CATALOG: list[dict] = [
    {
        "dataset": "fact_orders", "owner": "data-engineering", "source": "order-stream",
        "classification": "internal", "retention_days": 2555,
        "description": "Cleansed restaurant order events, one row per order line.",
    },
    {
        "dataset": "dim_restaurant", "owner": "data-engineering", "source": "master-data",
        "classification": "internal", "retention_days": 2555,
        "description": "Restaurant master data: market and region hierarchy.",
    },
    {
        "dataset": "dim_menu_item", "owner": "menu-operations", "source": "master-data",
        "classification": "internal", "retention_days": 2555,
        "description": "Menu-item master data with SCD2 price history.",
    },
    {
        "dataset": "order_quarantine", "owner": "data-engineering", "source": "order-stream",
        "classification": "restricted", "retention_days": 90,
        "description": "Quarantined order events with the reason they failed quality.",
    },
]

# Role-based access: which roles may read which classification.
ACCESS = {
    "data-engineer": {"internal", "restricted"},
    "analyst": {"internal"},
    "auditor": {"internal", "restricted"},
}


@dataclass
class GovernanceReport:
    master_data_ok: bool
    sla: dict
    access_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "master_data_ok": self.master_data_ok,
            "sla": self.sla,
            "access_violations": self.access_violations,
        }


def check_master_data(fact: pd.DataFrame) -> bool:
    """Every restaurant and menu code in the fact table must exist in master data."""
    if fact.empty:
        return True
    bad_restaurants = set(fact["restaurant_id"]) - set(RESTAURANTS)
    bad_menu = set(fact["menu_code"]) - set(MENU)
    return not bad_restaurants and not bad_menu


def check_sla(clean: int, quarantined: int, late: int, total: int,
              unique_total: int | None = None) -> dict:
    """Quality SLAs: completeness, accuracy (clean share), timeliness (late share).

    Completeness is measured against unique order ids (re-deliveries do not
    count as missing orders); accuracy against rows that reached quality;
    timeliness against all produced events.
    """
    unique_total = unique_total if unique_total is not None else total
    completeness = clean / unique_total if unique_total else 1.0
    accuracy = clean / (clean + quarantined) if (clean + quarantined) else 1.0
    timeliness = 1.0 - (late / total if total else 0.0)
    return {
        "completeness": round(completeness, 4),
        "accuracy": round(accuracy, 4),
        "timeliness": round(timeliness, 4),
        "sla_met": completeness >= 0.95 and accuracy >= 0.95 and timeliness >= 0.90,
    }


def check_access(role: str, dataset: str) -> bool:
    """Least-privilege read check: role may read the dataset's classification."""
    entry = next((d for d in CATALOG if d["dataset"] == dataset), None)
    if entry is None:
        return False
    return entry["classification"] in ACCESS.get(role, set())
