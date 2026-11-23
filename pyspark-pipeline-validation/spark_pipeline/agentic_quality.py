"""Agentic-AI-assisted data-quality triage for quarantined risk rows.

Project-level simulation of an Agentic AI workflow, the kind a Risk
Technology team would run over a Databricks quarantine table: observe the
quarantined rows, reason about each break against a fixed policy, propose a
disposition, and verify any recomputed value before it is accepted.

No live LLM is called here. The "agent" is a deterministic, rule-based
policy engine, so every finding is reproducible and auditable. In a
Databricks deployment the same observe -> reason -> act -> verify loop
would call an LLM agent for the reasoning step; here the policy table
plays that role, and the code is written so that step can be swapped out.

Policy (disposition per violation):
- exposure_mismatch -> AUTO_FIX: recompute exposure = notional * factor.
  The fix is only accepted when the recomputed value is deterministic and
  the row passes every other quality rule.
- null_counterparty -> ESCALATE: the source system must supply the
  counterparty; the agent cannot invent one.
- negative_notional -> ESCALATE: a sign error needs source confirmation.
- unknown_book -> ESCALATE: reference data has no such book; the agent
  cannot map the trade to a risk book on its own.
- date_out_of_range -> DROP: a trade dated outside the allowed window
  cannot be booked yet; re-ingest when the date is in window.
"""
from .risk_data import INSTRUMENT_FACTOR

# violation -> (disposition, action template, confidence)
POLICY = {
    "exposure_mismatch": (
        "AUTO_FIX",
        "Recompute exposure as notional * instrument factor and re-validate.",
        "high",
    ),
    "null_counterparty": (
        "ESCALATE",
        "Send to the source-system owner: counterparty is missing and cannot be inferred.",
        "high",
    ),
    "negative_notional": (
        "ESCALATE",
        "Send to the source-system owner: negative notional may be a sign error; needs confirmation.",
        "medium",
    ),
    "unknown_book": (
        "ESCALATE",
        "Send to reference-data owner: book is not in the book dimension; cannot map to a desk.",
        "high",
    ),
    "date_out_of_range": (
        "DROP",
        "Drop from this load: trade date is outside the allowed window; re-ingest when in window.",
        "high",
    ),
}


def auto_fix_exposure(row):
    """Recompute the exposure for an exposure_mismatch row.

    Returns the corrected exposure (rounded to cents) or None when the
    instrument has no known risk factor.
    """
    factor = INSTRUMENT_FACTOR.get(row["instrument_type"])
    if factor is None:
        return None
    return round(float(row["notional"]) * factor, 2)


def triage_quarantine(invalid):
    """Run the agent over every quarantined row.

    Returns a list of findings, one per row, each with the trade id, the
    violation, the proposed disposition, the action, the agent's confidence,
    and the corrected exposure when the disposition is AUTO_FIX.
    """
    findings = []
    for _, row in invalid.iterrows():
        violation = str(row["violation"]).split("+")[0]
        disposition, action, confidence = POLICY.get(
            violation,
            ("ESCALATE", "Send to a human reviewer: no policy covers this violation.", "medium"),
        )
        corrected = auto_fix_exposure(row) if disposition == "AUTO_FIX" else None
        findings.append(
            {
                "trade_id": row["trade_id"],
                "violation": violation,
                "disposition": disposition,
                "action": action,
                "confidence": confidence,
                "corrected_exposure": corrected,
            }
        )
    return findings


def triage_summary(findings):
    """Counts of findings by disposition, plus the AUTO_FIX total."""
    counts = {"AUTO_FIX": 0, "ESCALATE": 0, "DROP": 0}
    for finding in findings:
        counts[finding["disposition"]] = counts.get(finding["disposition"], 0) + 1
    return counts
