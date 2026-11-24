"""Compliance model inventory and validation governance.

A model risk office cannot defend what it cannot inventory. The
register tracks every compliance model through its lifecycle and
flags governance gaps: overdue validation, missing owner, or open
high-severity findings on a model still in use.
"""

from dataclasses import dataclass, field

RISK_TIERS = {"High": 365, "Medium": 730, "Low": 1095}


def validation_cadence_days(tier):
    """Days between full validations for a risk tier."""
    return RISK_TIERS[tier]


@dataclass
class ComplianceModel:
    model_id: str
    name: str
    purpose: str
    tier: str  # High / Medium / Low
    owner: str = ""
    stage: str = "Development"  # Development / Validation / In Use / Retired
    days_since_validation: int = 0
    open_high_findings: int = 0

    def validation_overdue(self):
        return self.days_since_validation > validation_cadence_days(self.tier)

    def governance_gaps(self):
        gaps = []
        if not self.owner:
            gaps.append("missing owner")
        if self.validation_overdue():
            gaps.append("validation overdue")
        if self.stage == "In Use" and self.open_high_findings > 0:
            gaps.append(f"{self.open_high_findings} open high finding(s) while in use")
        return gaps


@dataclass
class ModelInventory:
    models: list = field(default_factory=list)

    def add(self, model):
        self.models.append(model)

    def by_tier(self, tier):
        return [m for m in self.models if m.tier == tier]

    def overdue(self):
        return [m for m in self.models if m.validation_overdue()]

    def gaps_report(self):
        """One row per model with a governance gap, else 'clean'."""
        rows = []
        for m in self.models:
            gaps = m.governance_gaps()
            rows.append(
                {
                    "model_id": m.model_id,
                    "name": m.name,
                    "tier": m.tier,
                    "stage": m.stage,
                    "gaps": gaps if gaps else ["clean"],
                }
            )
        return rows
