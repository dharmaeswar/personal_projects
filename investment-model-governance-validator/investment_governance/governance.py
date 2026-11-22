"""Model inventory and governance: the second line of defence.

A model inventory register with lifecycle stages, validation cadence,
and an SR 11-7-style validation report: findings with severity, an
effective-challenge checklist, and an overall opinion. This is the
governance half of the Vanguard Model Governance role — not a pricing
check, but the control framework around the models.
"""

from dataclasses import dataclass, field

VALID_STAGES = ("development", "validation", "approved", "in_use", "restricted", "retired")
VALID_TIERS = ("low", "medium", "high")
VALID_OPINIONS = ("Satisfactory", "Needs Improvement", "Unsatisfactory")


@dataclass
class Finding:
    """One validation finding with a severity and a remediation owner."""

    title: str
    severity: str  # High / Medium / Low
    detail: str
    owner: str = "Model Owner"

    def __post_init__(self):
        if self.severity not in ("High", "Medium", "Low"):
            raise ValueError("severity must be High, Medium or Low")


@dataclass
class ModelRecord:
    """One entry in the model inventory register."""

    model_id: str
    name: str
    model_type: str  # e.g. "alpha_signal", "portfolio_optimizer", "risk_var"
    owner: str
    stage: str
    risk_tier: str  # low / medium / high
    months_since_validation: int
    findings: list = field(default_factory=list)

    def __post_init__(self):
        if self.stage not in VALID_STAGES:
            raise ValueError(f"unknown stage: {self.stage}")
        if self.risk_tier not in VALID_TIERS:
            raise ValueError(f"unknown risk tier: {self.risk_tier}")
        if self.months_since_validation < 0:
            raise ValueError("months_since_validation must be >= 0")


def validation_due(record, cadence_months=None):
    """True when a model is past its validation cadence.

    Default cadence: high-tier 12 months, medium 18, low 24.
    """
    cadence = cadence_months or {"high": 12, "medium": 18, "low": 24}
    return record.months_since_validation > cadence[record.risk_tier]


def inventory_gaps(records):
    """Governance gaps across the whole register.

    Returns a list of human-readable gap descriptions.
    """
    gaps = []
    for rec in records:
        if validation_due(rec):
            gaps.append(
                f"{rec.model_id} ({rec.name}): validation overdue — "
                f"{rec.months_since_validation} months since last validation"
            )
        if not rec.owner.strip():
            gaps.append(f"{rec.model_id} ({rec.name}): no accountable owner")
        if rec.stage == "in_use" and any(
            f.severity == "High" for f in rec.findings
        ):
            gaps.append(
                f"{rec.model_id} ({rec.name}): in use with an open High finding"
            )
        if rec.stage == "approved" and rec.months_since_validation > 12:
            gaps.append(
                f"{rec.model_id} ({rec.name}): approved over a year ago, "
                "re-validation not recorded"
            )
    return gaps


def effective_challenge_checklist():
    """The checks an independent reviewer must evidence for a model."""
    return [
        "Conceptual soundness: theory, assumptions and limitations documented",
        "Data quality: inputs checked for completeness, accuracy and lineage",
        "Implementation: code reviewed against the documented methodology",
        "Outcomes analysis: backtest results compared with model predictions",
        "Sensitivity and stress: key inputs shocked, results within tolerance",
        "Benchmarking: challenger or benchmark model compared",
        "Ongoing monitoring: thresholds, drift checks and escalation defined",
        "Governance: inventory entry, owner, tier and approval recorded",
    ]


def validation_opinion(findings):
    """Overall opinion from the finding severities."""
    severities = [f.severity for f in findings]
    if "High" in severities:
        return "Unsatisfactory"
    if "Medium" in severities:
        return "Needs Improvement"
    return "Satisfactory"


def build_validation_report(record, findings, checks_evidence):
    """Assemble an SR 11-7-style validation report dict for one model."""
    opinion = validation_opinion(findings)
    checklist = effective_challenge_checklist()
    evidenced = [c for c in checklist if checks_evidence.get(c, False)]
    report = {
        "model_id": record.model_id,
        "model_name": record.name,
        "model_type": record.model_type,
        "owner": record.owner,
        "stage": record.stage,
        "risk_tier": record.risk_tier,
        "opinion": opinion,
        "findings": [
            {"title": f.title, "severity": f.severity, "detail": f.detail, "owner": f.owner}
            for f in findings
        ],
        "checklist_evidenced": len(evidenced),
        "checklist_total": len(checklist),
        "checklist_missing": [c for c in checklist if not checks_evidence.get(c, False)],
    }
    return report
