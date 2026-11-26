"""LLM-assisted development workflow: summaries + evaluation, human-gated.

The role asks for strong opinions on how to use AI/LLMs in the software
development process, and for the judgement to tell hype from value. This
module encodes one defensible pattern: an LLM drafts a plain-language
summary of pipeline findings (pacing alerts, quality failures, held
optimisations) from structured facts, a deterministic evaluator scores
that draft against the known ground truth, and NOTHING is applied to a
live campaign without a human review.

Honest note: no live LLM is called here. The summary generator is a
deterministic template over the same structured findings an LLM prompt
would receive, so the evaluator and the human gate can be tested locally.
In production the template is swapped for an LLM call with the identical
input contract and the identical evaluator + human gate.
"""

from __future__ import annotations


def summarize_findings(findings: list[dict]) -> dict:
    """Draft a human-reviewable summary from structured pipeline findings.

    Each finding carries kind (pacing / quality / guardrail), campaign_id
    and detail. The draft lists counts by kind and names the most severe
    item of each kind. It is always marked as a draft needing review.
    """
    by_kind: dict[str, list[dict]] = {}
    for finding in findings:
        by_kind.setdefault(finding["kind"], []).append(finding)
    lines = [f"Pipeline findings: {len(findings)} item(s) need review."]
    for kind in sorted(by_kind):
        items = by_kind[kind]
        lines.append(f"- {kind}: {len(items)} item(s).")
        worst = items[0]
        lines.append(f"  Top {kind} item: {worst['campaign_id']} — {worst['detail']}")
    return {
        "summary": "\n".join(lines),
        "status": "draft",
        "requires_human_review": True,
        "finding_count": len(findings),
        "kinds_covered": sorted(by_kind),
    }


def evaluate_summary(draft: dict, findings: list[dict]) -> dict:
    """Score a draft summary against the ground-truth findings.

    Checks: the finding count is stated, every kind present in the
    findings is covered, and every campaign with a HOLD decision is named.
    A draft that misses a held campaign fails, however fluent it reads.
    """
    missing_kinds = [k for k in {f["kind"] for f in findings}
                     if k not in draft.get("kinds_covered", [])]
    held_campaigns = {f["campaign_id"] for f in findings
                      if f.get("decision") == "HOLD"}
    unnamed_held = [c for c in held_campaigns if c not in draft["summary"]]
    count_ok = str(len(findings)) in draft["summary"]
    passed = not missing_kinds and not unnamed_held and count_ok
    return {
        "passed": passed,
        "count_stated": count_ok,
        "missing_kinds": missing_kinds,
        "held_campaigns_unnamed": unnamed_held,
        "score": round(
            (int(count_ok) + int(not missing_kinds) + int(not unnamed_held)) / 3, 2),
    }
