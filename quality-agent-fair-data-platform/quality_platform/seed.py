"""Synthetic, seeded Quality-domain data.

Batch release records, deviation reports and CAPA records for a fictional
drug-substance product line. Every value is invented in code; nothing here
is real Amgen or other company data, and nothing ran in production.
"""

from datetime import datetime

# 12 batch records: release cycle time in days, per quarter.
BATCHES = [
    {"batch_id": "B-101", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q2", "release_cycle_days": 18, "deviations": 1, "capa": 0},
    {"batch_id": "B-102", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q2", "release_cycle_days": 21, "deviations": 2, "capa": 1},
    {"batch_id": "B-103", "product_line": "substance-a", "site": "site-2",
     "quarter": "Q2", "release_cycle_days": 19, "deviations": 0, "capa": 0},
    {"batch_id": "B-104", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q2", "release_cycle_days": 22, "deviations": 1, "capa": 0},
    {"batch_id": "B-105", "product_line": "substance-a", "site": "site-2",
     "quarter": "Q2", "release_cycle_days": 20, "deviations": 1, "capa": 0},
    {"batch_id": "B-106", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q2", "release_cycle_days": 20, "deviations": 0, "capa": 0},
    {"batch_id": "B-201", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q3", "release_cycle_days": 27, "deviations": 3, "capa": 1},
    {"batch_id": "B-202", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q3", "release_cycle_days": 29, "deviations": 2, "capa": 1},
    {"batch_id": "B-203", "product_line": "substance-a", "site": "site-2",
     "quarter": "Q3", "release_cycle_days": 24, "deviations": 2, "capa": 0},
    {"batch_id": "B-204", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q3", "release_cycle_days": 31, "deviations": 4, "capa": 2},
    {"batch_id": "B-205", "product_line": "substance-a", "site": "site-2",
     "quarter": "Q3", "release_cycle_days": 26, "deviations": 1, "capa": 0},
    {"batch_id": "B-206", "product_line": "substance-a", "site": "site-1",
     "quarter": "Q3", "release_cycle_days": 28, "deviations": 3, "capa": 1},
]

DEVIATIONS = [
    {"deviation_id": "D-01", "batch_id": "B-201", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-02", "batch_id": "B-201", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-03", "batch_id": "B-202", "category": "documentation",
     "severity": "major", "quarter": "Q3"},
    {"deviation_id": "D-04", "batch_id": "B-203", "category": "equipment",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-05", "batch_id": "B-204", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-06", "batch_id": "B-204", "category": "method",
     "severity": "major", "quarter": "Q3"},
    {"deviation_id": "D-07", "batch_id": "B-204", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-08", "batch_id": "B-205", "category": "equipment",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-09", "batch_id": "B-206", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
    {"deviation_id": "D-10", "batch_id": "B-206", "category": "documentation",
     "severity": "minor", "quarter": "Q3"},
]

CAPAS = [
    {"capa_id": "C-01", "deviation_id": "D-03", "status": "open",
     "due_days": 30, "quarter": "Q3"},
    {"capa_id": "C-02", "deviation_id": "D-06", "status": "open",
     "due_days": 45, "quarter": "Q3"},
    {"capa_id": "C-03", "deviation_id": "D-01", "status": "closed",
     "due_days": 14, "quarter": "Q3"},
]

# The FAIR products registered over this data.
PRODUCTS = [
    {
        "product_id": "batch-release",
        "name": "Batch Release Cycle Time",
        "domain": "quality",
        "owner": "quality-analytics",
        "description": "Release cycle time, deviations and CAPA counts per batch",
        "keywords": ["batch", "release", "cycle time", "deviation", "capa"],
        "schema": [
            {"name": "batch_id", "type": "string"},
            {"name": "quarter", "type": "string"},
            {"name": "release_cycle_days", "type": "integer"},
            {"name": "deviations", "type": "integer"},
            {"name": "capa", "type": "integer"},
        ],
        "freshness_sla_hours": 24,
        "quality_score": 94,
        "access_level": "internal",
        "version": "1.2.0",
        "status": "live",
        "last_updated": datetime(2026, 11, 25, 8, 0),
    },
    {
        "product_id": "deviation-register",
        "name": "Deviation Register",
        "domain": "quality",
        "owner": "quality-operations",
        "description": "All deviation reports with category, severity and batch link",
        "keywords": ["deviation", "register", "severity", "category"],
        "schema": [
            {"name": "deviation_id", "type": "string"},
            {"name": "batch_id", "type": "string"},
            {"name": "category", "type": "string"},
            {"name": "severity", "type": "string"},
        ],
        "freshness_sla_hours": 24,
        "quality_score": 91,
        "access_level": "internal",
        "version": "2.0.1",
        "status": "live",
        "last_updated": datetime(2026, 11, 25, 8, 0),
    },
    {
        "product_id": "capa-tracker",
        "name": "CAPA Tracker",
        "domain": "quality",
        "owner": "quality-assurance",
        "description": "Corrective and preventive actions with status and due dates",
        "keywords": ["capa", "corrective", "preventive", "action"],
        "schema": [
            {"name": "capa_id", "type": "string"},
            {"name": "deviation_id", "type": "string"},
            {"name": "status", "type": "string"},
            {"name": "due_days", "type": "integer"},
        ],
        "freshness_sla_hours": 48,
        "quality_score": 88,
        "access_level": "restricted",
        "version": "1.0.3",
        "status": "live",
        "last_updated": datetime(2026, 11, 24, 8, 0),
    },
]

LINEAGE = {
    "batch-release": [
        {"source": "lims-batch-extract", "transform": "normalize_cycle_time v3",
         "contract_version": "1.2.0"},
        {"source": "qms-deviation-feed", "transform": "join_deviation_counts v1",
         "contract_version": "1.2.0"},
    ],
    "deviation-register": [
        {"source": "qms-deviation-feed", "transform": "classify_severity v2",
         "contract_version": "2.0.1"},
    ],
    "capa-tracker": [
        {"source": "qms-capa-feed", "transform": "dedupe_capa v1",
         "contract_version": "1.0.3"},
    ],
}


def build_registry():
    """A FairRegistry pre-loaded with the three seeded products."""
    from quality_platform.fair import FairRegistry
    registry = FairRegistry()
    for product in PRODUCTS:
        registry.register(product, lineage=LINEAGE[product["product_id"]])
    return registry


def mean(values):
    return sum(values) / len(values) if values else None


def batch_metrics(quarter=None):
    """Aggregate release metrics, optionally for one quarter."""
    rows = [b for b in BATCHES if quarter is None or b["quarter"] == quarter]
    if not rows:
        return None
    return {
        "quarter": quarter or "all",
        "batches": len(rows),
        "mean_release_cycle_days": round(mean([b["release_cycle_days"] for b in rows]), 1),
        "total_deviations": sum(b["deviations"] for b in rows),
        "total_capa": sum(b["capa"] for b in rows),
        "max_release_cycle_days": max(b["release_cycle_days"] for b in rows),
    }


def deviation_breakdown(quarter=None):
    """Count deviations by category, optionally for one quarter."""
    rows = [d for d in DEVIATIONS if quarter is None or d["quarter"] == quarter]
    counts = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    return {"quarter": quarter or "all", "total": len(rows), "by_category": counts}
