"""Model approval workflow: gate validation evidence into an approval decision.

Mirrors how a bank model-risk team runs a model approval process: the model
is registered in an inventory record, the independent validation evidence
(outcomes analysis, calibration, drift, fairness) is checked against
documented thresholds, and the outcome is one of APPROVED,
APPROVED_WITH_CONDITIONS, or NOT_APPROVED, with a sign-off trail. Soft
breaches (between the condition and rejection bands) become conditions with
owners and due dates; hard breaches block approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

APPROVED = "APPROVED"
APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"
NOT_APPROVED = "NOT_APPROVED"

PASS = "PASS"
CONDITION = "CONDITION"
FAIL = "FAIL"


@dataclass
class ApprovalThresholds:
    """Evidence gates for model approval (documented, overridable)."""

    min_roc_auc: float = 0.70          # below -> NOT_APPROVED
    min_ks: float = 0.20               # below -> NOT_APPROVED
    min_outcomes: int = 200            # fewer test outcomes -> NOT_APPROVED
    calibration_gap_condition: float = 0.02   # above -> condition
    calibration_gap_fail: float = 0.05        # above -> NOT_APPROVED
    psi_condition: float = 0.10               # above -> condition
    psi_fail: float = 0.25                    # above -> NOT_APPROVED
    fairness_gap_condition: float = 0.05      # above -> condition
    fairness_gap_fail: float = 0.10           # above -> NOT_APPROVED


@dataclass
class ValidationEvidence:
    """The independent-validation numbers an approval decision rests on."""

    roc_auc: float
    ks: float
    calibration_gap: float   # max |mean predicted - observed| across deciles
    max_psi: float           # worst feature PSI between reference and current
    max_flag_rate_gap: float  # worst fairness flag-rate gap across segments
    n_outcomes: int          # number of test outcomes behind the evidence


@dataclass
class ModelRecord:
    """One row of the model inventory an approval request is filed against."""

    model_id: str
    name: str
    owner: str
    model_tier: int          # 1 = highest risk / most scrutiny
    purpose: str


@dataclass
class ApprovalDecision:
    decision: str
    checks: list = field(default_factory=list)      # per-gate result dicts
    conditions: list = field(default_factory=list)  # required follow-ups
    findings: list = field(default_factory=list)    # blocking problems


def evidence_from_results(
    results: dict, drift: pd.DataFrame, max_flag_gap: float, n_outcomes: int
) -> ValidationEvidence:
    """Build approval evidence from the champion model's validation output."""
    champ = results["champion"]
    calibration = champ["calibration"]
    gap = float((calibration["mean_predicted"] - calibration["observed_rate"]).abs().max())
    return ValidationEvidence(
        roc_auc=float(champ["roc_auc"]),
        ks=float(champ["ks"]),
        calibration_gap=gap,
        max_psi=float(drift["psi"].max()),
        max_flag_rate_gap=float(max_flag_gap),
        n_outcomes=int(n_outcomes),
    )


def _band(value: float, condition_above: float, fail_above: float) -> str:
    if value > fail_above:
        return FAIL
    if value > condition_above:
        return CONDITION
    return PASS


def _floor(value: float, minimum: float) -> str:
    return PASS if value >= minimum else FAIL


def evaluate_approval(
    evidence: ValidationEvidence,
    thresholds: ApprovalThresholds | None = None,
) -> ApprovalDecision:
    """Apply the approval gates to validation evidence.

    Any FAIL gate blocks approval. Any CONDITION gate approves the model
    only with documented follow-up conditions. All PASS approves outright.
    """
    t = thresholds or ApprovalThresholds()
    checks = []

    def add(name: str, value: float, status: str, detail: str) -> None:
        checks.append(
            {"check": name, "value": value, "status": status, "detail": detail}
        )

    add(
        "discrimination_auc",
        evidence.roc_auc,
        _floor(evidence.roc_auc, t.min_roc_auc),
        f"ROC-AUC {evidence.roc_auc:.3f} vs minimum {t.min_roc_auc:.2f}",
    )
    add(
        "discrimination_ks",
        evidence.ks,
        _floor(evidence.ks, t.min_ks),
        f"KS {evidence.ks:.3f} vs minimum {t.min_ks:.2f}",
    )
    add(
        "outcomes_sample_size",
        float(evidence.n_outcomes),
        _floor(float(evidence.n_outcomes), float(t.min_outcomes)),
        f"{evidence.n_outcomes} test outcomes vs minimum {t.min_outcomes}",
    )
    add(
        "calibration",
        evidence.calibration_gap,
        _band(evidence.calibration_gap, t.calibration_gap_condition, t.calibration_gap_fail),
        f"max decile calibration gap {evidence.calibration_gap:.3f} "
        f"(condition > {t.calibration_gap_condition:.2f}, fail > {t.calibration_gap_fail:.2f})",
    )
    add(
        "population_stability",
        evidence.max_psi,
        _band(evidence.max_psi, t.psi_condition, t.psi_fail),
        f"max feature PSI {evidence.max_psi:.3f} "
        f"(condition > {t.psi_condition:.2f}, fail > {t.psi_fail:.2f})",
    )
    add(
        "fairness_flag_gap",
        evidence.max_flag_rate_gap,
        _band(evidence.max_flag_rate_gap, t.fairness_gap_condition, t.fairness_gap_fail),
        f"max segment flag-rate gap {evidence.max_flag_rate_gap:.3f} "
        f"(condition > {t.fairness_gap_condition:.2f}, fail > {t.fairness_gap_fail:.2f})",
    )

    findings = [c["detail"] for c in checks if c["status"] == FAIL]
    conditions = [
        f"Remediate and re-check before next review: {c['detail']}"
        for c in checks
        if c["status"] == CONDITION
    ]
    if findings:
        decision = NOT_APPROVED
    elif conditions:
        decision = APPROVED_WITH_CONDITIONS
    else:
        decision = APPROVED
    return ApprovalDecision(
        decision=decision, checks=checks, conditions=conditions, findings=findings
    )


def sign_off(
    record: ModelRecord,
    decision: ApprovalDecision,
    validator: str,
    sign_date: str,
) -> dict:
    """Record one sign-off trail entry for an approval decision."""
    return {
        "model_id": record.model_id,
        "model_name": record.name,
        "owner": record.owner,
        "model_tier": record.model_tier,
        "validator": validator,
        "decision": decision.decision,
        "date": sign_date,
        "n_conditions": len(decision.conditions),
        "n_findings": len(decision.findings),
    }


def approval_trail_table(trail: list) -> pd.DataFrame:
    """Sign-off trail as a table (one row per decided model)."""
    return pd.DataFrame(trail)


def build_approval_section(
    record: ModelRecord, decision: ApprovalDecision, trail_entry: dict
) -> str:
    """Render the model-approval section of the validation report."""
    lines = [
        "",
        "=" * 70,
        "11. MODEL APPROVAL WORKFLOW (inventory, evidence gates, sign-off)",
        "=" * 70,
        f"Model: {record.model_id} — {record.name}",
        f"Owner: {record.owner} | Tier: {record.model_tier} | Purpose: {record.purpose}",
        "",
        "Evidence gates:",
    ]
    for c in decision.checks:
        lines.append(f"  [{c['status']:<9}] {c['check']}: {c['detail']}")
    lines.append("")
    lines.append(f"Decision: {decision.decision}")
    if decision.conditions:
        lines.append("Conditions:")
        for cond in decision.conditions:
            lines.append(f"  - {cond}")
    if decision.findings:
        lines.append("Blocking findings:")
        for finding in decision.findings:
            lines.append(f"  - {finding}")
    lines.append(
        f"Sign-off: {trail_entry['validator']} on {trail_entry['date']} "
        f"({trail_entry['n_conditions']} conditions, "
        f"{trail_entry['n_findings']} findings)."
    )
    return "\n".join(lines) + "\n"
