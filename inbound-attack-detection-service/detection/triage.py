"""Deterministic triage "agent" for flagged messages.

This is a simulation of an agentic triage workflow, not a real LLM:
the steps are fixed and auditable — gather signals, check the allow
and block lists, apply a decision policy, and return a verdict with a
rationale. Same input always produces the same verdict.
"""

from __future__ import annotations

from .features import extract_features

# Synthetic tenant lists. In production these come from the security
# team's allow/block list store; here they are fixed fixtures.
ALLOWLIST_DOMAINS = {"acmecorp.com", "acme-partners.com", "vendor-invoices.example"}
BLOCKLIST_DOMAINS = {"acmec0rp.com", "acme-secure-login.xyz", "invoice-pay.top"}
BLOCKLIST_SENDERS = {"billing@acmec0rp.com", "ceo@acme-secure-login.xyz"}


def _domain_of(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def triage_message(
    message: dict,
    score_result: dict,
    allowlist: set[str] | None = None,
    blocklist_domains: set[str] | None = None,
    blocklist_senders: set[str] | None = None,
) -> dict:
    """Triage one flagged message.

    Returns a verdict dict: verdict (allow / quarantine / escalate),
    action, confidence, the ordered steps the agent "took", and a
    human-readable rationale.
    """
    allow = ALLOWLIST_DOMAINS if allowlist is None else allowlist
    blocked_domains = BLOCKLIST_DOMAINS if blocklist_domains is None else blocklist_domains
    blocked_senders = BLOCKLIST_SENDERS if blocklist_senders is None else blocklist_senders

    sender = (message.get("sender") or "").strip().lower()
    sender_domain = _domain_of(sender)
    features = extract_features(message)
    score = score_result.get("score", 0.0)

    steps: list[dict] = []
    rationale: list[str] = []

    # Step 1: gather signals.
    top = score_result.get("top_signals", [])
    steps.append({
        "step": "gather_signals",
        "detail": f"risk score {score:.3f}; top signals: "
                  + ", ".join(s["feature"] for s in top[:3]) if top else "risk score %.3f; no strong signals" % score,
    })
    rationale.append(f"Classifier risk score is {score:.3f}.")

    # Step 2: allow-list check — a known-good sender domain overrides a
    # borderline score, but never a block-list hit.
    if sender_domain in allow:
        steps.append({"step": "check_allowlist", "detail": f"{sender_domain} is allowlisted"})
        rationale.append(f"Sender domain {sender_domain} is on the tenant allowlist.")
        if score < 0.8:
            return _verdict("allow", "deliver", 0.85, steps, rationale, features)
        rationale.append("Score is high despite the allowlist entry; escalating for review.")

    # Step 3: block-list check — deterministic, highest precedence.
    if sender in blocked_senders or sender_domain in blocked_domains:
        steps.append({"step": "check_blocklist", "detail": f"{sender} / {sender_domain} is blocklisted"})
        rationale.append(f"Sender {sender} matches the blocklist.")
        return _verdict("quarantine", "quarantine_and_block_sender", 0.98, steps, rationale, features)

    steps.append({"step": "check_blocklist", "detail": "no blocklist match"})

    # Step 4: policy decision on the score and hard signals.
    hard_attack = (
        features["display_name_spoof"]
        or features["lookalike_domain"]
        or features["has_risky_attachment"]
        or features["auth_failures"] >= 3
    )
    if score >= 0.8 or hard_attack:
        steps.append({"step": "apply_policy", "detail": "high risk or hard attack signal"})
        rationale.append("High risk score or a hard attack signal (spoof / lookalike / risky attachment / full auth failure).")
        return _verdict("quarantine", "quarantine", 0.9, steps, rationale, features)
    if score >= 0.5:
        steps.append({"step": "apply_policy", "detail": "medium risk — needs a human"})
        rationale.append("Medium risk: not conclusive enough to quarantine automatically.")
        return _verdict("escalate", "escalate_to_soc_analyst", 0.7, steps, rationale, features)

    steps.append({"step": "apply_policy", "detail": "low risk — deliver"})
    rationale.append("Low risk and no hard attack signal.")
    return _verdict("allow", "deliver", 0.8, steps, rationale, features)


def _verdict(verdict, action, confidence, steps, rationale, features):
    return {
        "verdict": verdict,
        "action": action,
        "confidence": round(confidence, 2),
        "steps": steps,
        "rationale": " ".join(rationale),
        "key_features": {
            k: features[k]
            for k in (
                "display_name_spoof", "lookalike_domain", "auth_failures",
                "risky_attachment_count", "suspicious_tld_count",
            )
        },
    }
