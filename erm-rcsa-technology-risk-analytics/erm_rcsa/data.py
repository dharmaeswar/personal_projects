"""Seeded synthetic data for the ERM / RCSA technology-risk analytics project.

All data is synthetic, deterministic (seeded), and fictional. No real
positions, losses, controls, or bank data are used, and nothing here is a
claim about any real company or its systems.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SEED = 20261127
AS_OF_DATE = "2026-11-27"


@dataclass(frozen=True)
class Risk:
    risk_id: str
    name: str
    category: str  # operational | financial | strategic | technology
    source: str  # IT | IS | TP | DM (which data source the risk came from)
    likelihood: int  # 1-5
    impact: int  # 1-5


@dataclass(frozen=True)
class Control:
    control_id: str
    risk_id: str
    name: str
    design: str  # Effective | Needs Improvement | Ineffective
    sample_size: int
    exceptions: int  # failed samples in Test of Effectiveness


@dataclass(frozen=True)
class LossEvent:
    event_id: str
    category: str
    source: str  # IT | IS | TP | DM
    amount: float
    event_date: str


@dataclass(frozen=True)
class Kri:
    kri_id: str
    name: str
    unit: str
    higher_is_worse: bool
    warning: float
    breach: float
    history: tuple  # oldest -> newest quarterly readings


@dataclass(frozen=True)
class FrameworkRequirement:
    req_id: str
    framework: str  # COBIT | NIST | ITIL | DCAM | DMBOK
    function: str  # 1LOD function being assessed
    requirement: str
    weight: int = 1


def generate_risks():
    """RCSA risk register: 14 risks across the four technology-risk sources."""
    return [
        Risk("R-01", "Unpatched critical vulnerabilities in production", "technology", "IS", 4, 5),
        Risk("R-02", "Third-party vendor service outage", "operational", "TP", 3, 4),
        Risk("R-03", "Incomplete data lineage for regulatory reporting", "technology", "DM", 4, 4),
        Risk("R-04", "Failed change without rollback plan", "operational", "IT", 3, 4),
        Risk("R-05", "Phishing-driven credential compromise", "technology", "IS", 4, 4),
        Risk("R-06", "Vendor concentration in payment processing", "strategic", "TP", 4, 5),
        Risk("R-07", "Stale reference data in risk calculations", "financial", "DM", 3, 3),
        Risk("R-08", "Backup restore never tested end to end", "operational", "IT", 2, 5),
        Risk("R-09", "Excess privileged access without review", "technology", "IS", 4, 3),
        Risk("R-10", "Vendor contract missing exit clause", "strategic", "TP", 2, 4),
        Risk("R-11", "Manual reconciliation of GL postings", "financial", "DM", 3, 3),
        Risk("R-12", "Single point of failure in network core", "operational", "IT", 2, 5),
        Risk("R-13", "Outdated encryption on data at rest", "technology", "IS", 3, 4),
        Risk("R-14", "Missing data quality checks on feeds", "technology", "DM", 4, 3),
    ]


def generate_controls():
    """Controls mapped to risks, with Test of Effectiveness samples."""
    return [
        Control("C-01", "R-01", "Weekly patch cycle with SLA tracking", "Effective", 25, 1),
        Control("C-02", "R-01", "Vulnerability scan exception review", "Needs Improvement", 20, 4),
        Control("C-03", "R-02", "Vendor failover test each quarter", "Effective", 12, 0),
        Control("C-04", "R-03", "Lineage documented for critical reports", "Needs Improvement", 15, 3),
        Control("C-05", "R-04", "Change advisory board approval", "Effective", 30, 2),
        Control("C-06", "R-05", "Phishing simulation and training", "Effective", 40, 3),
        Control("C-07", "R-06", "Vendor concentration limit monitoring", "Needs Improvement", 10, 2),
        Control("C-08", "R-07", "Reference-data freshness check", "Effective", 20, 1),
        Control("C-09", "R-08", "Annual restore test with sign-off", "Ineffective", 8, 5),
        Control("C-10", "R-09", "Quarterly privileged-access review", "Effective", 25, 2),
        Control("C-11", "R-10", "Contract clause checklist at renewal", "Needs Improvement", 10, 1),
        Control("C-12", "R-11", "Daily GL reconciliation with breaks queue", "Effective", 30, 1),
        Control("C-13", "R-12", "Network redundancy design review", "Effective", 12, 0),
        Control("C-14", "R-13", "Encryption standard enforcement scan", "Needs Improvement", 18, 4),
        Control("C-15", "R-14", "Feed completeness check before load", "Effective", 25, 1),
        Control("C-16", "R-05", "MFA enforced on all remote access", "Effective", 40, 0),
    ]


def generate_loss_events():
    """Operational-loss, compliance, and financial-exposure events (seeded)."""
    rng = random.Random(SEED)
    categories = ["operational", "compliance", "financial"]
    sources = ["IT", "IS", "TP", "DM"]
    events = []
    for i in range(36):
        events.append(
            LossEvent(
                event_id=f"LE-{i + 1:02d}",
                category=categories[i % 3],
                source=sources[rng.randrange(4)],
                amount=round(rng.uniform(500, 45000), 2),
                event_date=f"2026-{rng.randrange(1, 12):02d}-{rng.randrange(1, 28):02d}",
            )
        )
    # Planted case: one large technology loss that must surface as the top event.
    events.append(LossEvent("LE-37", "operational", "IS", 285000.00, "2026-10-14"))
    return events


def generate_kris():
    """KRIs/KPIs with six quarters of history; two are planted to breach/trend."""
    return [
        Kri("K-01", "Unpatched critical vulnerabilities (count)", "count", True,
            10, 20, (4, 6, 8, 12, 18, 24)),
        Kri("K-02", "Failed changes (% of all changes)", "%", True,
            5, 8, (3.1, 2.8, 3.4, 3.0, 2.9, 3.2)),
        Kri("K-03", "Vendor SLA breaches (count/quarter)", "count", True,
            3, 5, (1, 2, 1, 2, 4, 5)),
        Kri("K-04", "Data quality exceptions (% of feeds)", "%", True,
            2, 4, (1.2, 1.5, 1.1, 1.8, 2.6, 3.9)),
        Kri("K-05", "Backup restore test success (%)", "%", False,
            95, 90, (98, 97, 99, 96, 94, 91)),
        Kri("K-06", "Privileged access reviews on time (%)", "%", False,
            90, 80, (96, 94, 95, 93, 92, 91)),
        Kri("K-07", "Mean time to patch criticals (days)", "days", True,
            14, 30, (9, 11, 10, 13, 16, 19)),
        Kri("K-08", "Control test pass rate (%)", "%", False,
            90, 85, (93, 91, 92, 90, 89, 87)),
    ]


def generate_framework_requirements():
    """1LOD assessment checklist mapped to COBIT / NIST / ITIL / DCAM / DMBOK."""
    return [
        FrameworkRequirement("F-01", "COBIT", "IT Operations", "Change approval recorded before production release", 2),
        FrameworkRequirement("F-02", "COBIT", "IT Operations", "Access reviews completed on schedule", 2),
        FrameworkRequirement("F-03", "NIST", "Information Security", "Vulnerabilities patched within SLA", 3),
        FrameworkRequirement("F-04", "NIST", "Information Security", "Incident response plan tested annually", 2),
        FrameworkRequirement("F-05", "ITIL", "IT Operations", "Incident and problem records linked to changes", 1),
        FrameworkRequirement("F-06", "ITIL", "Service Management", "Service catalogue current for critical services", 1),
        FrameworkRequirement("F-07", "DCAM", "Data Management", "Critical data elements have a named owner", 2),
        FrameworkRequirement("F-08", "DCAM", "Data Management", "Data lineage documented for regulatory reports", 3),
        FrameworkRequirement("F-09", "DMBOK", "Data Management", "Data quality rules defined and monitored", 2),
        FrameworkRequirement("F-10", "DMBOK", "Data Management", "Reference data versioned and approved", 1),
        FrameworkRequirement("F-11", "COBIT", "Third Party", "Vendor risk tier reviewed at onboarding", 2),
        FrameworkRequirement("F-12", "NIST", "Third Party", "Vendor access revoked within 24h of exit", 2),
    ]


def generate_all():
    return {
        "risks": generate_risks(),
        "controls": generate_controls(),
        "loss_events": generate_loss_events(),
        "kris": generate_kris(),
        "framework_reqs": generate_framework_requirements(),
    }
