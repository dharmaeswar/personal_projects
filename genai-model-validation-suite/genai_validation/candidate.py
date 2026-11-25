"""Deterministic stand-ins for the GenAI models under validation.

No real LLM or API calls: the candidate is a fixed rule-based policy
with seeded faults, so every validation run is reproducible offline.
A model-backed generator plugs into the same ``generate()`` interface.
"""
from __future__ import annotations

import random

from .data import decision_rule

FACT_LABELS = {
    "credit_limit": "credit limit",
    "balance": "balance",
    "apr": "APR",
    "min_payment": "minimum payment",
    "months_delinquent": "months delinquent",
    "utilization": "utilization",
}


class CandidateModel:
    """LLM-style decision-support model: decision plus cited explanation.

    ``seed`` selects the sampling run. Seeds 0-2 are clean; higher seeds
    inject the faults a validator must catch: a hallucinated APR in the
    explanation (seed 3) and a misread utilization that flips the
    decision (seed 4). This mirrors a real GenAI failure pattern where
    the narrative cites numbers the source data does not support.
    ``prompt_variant="injection:<probe>"`` simulates a prompt-injection
    attempt: the candidate obeys a direct instruction override and a
    fake system message (decision forced to "approve"), but resists an
    instruction buried in retrieved text and a roleplay jailbreak.
    """

    name = "candidate-genai-v1"

    def generate(self, case: dict, seed: int = 0, prompt_variant: str = "base") -> dict:
        facts = dict(case["facts"])
        if prompt_variant == "reordered":
            facts = dict(reversed(list(facts.items())))
        elif prompt_variant == "paraphrased":
            facts = dict(facts)
        rng = random.Random(f"{case['case_id']}-{seed}-{prompt_variant}")
        decision = decision_rule(facts)
        cited = dict(facts)
        fault = None
        if prompt_variant.startswith("injection:"):
            # Seeded vulnerability: the candidate obeys direct instruction
            # overrides and system-message impersonation, but resists
            # injections buried in retrieved text and roleplay jailbreaks.
            probe = prompt_variant.split(":", 1)[1]
            if probe in ("direct-override", "system-impersonation"):
                decision = "approve"
                fault = "prompt_injection"
        if seed == 3:
            # Hallucination: explanation cites an APR never in the source.
            cited["apr"] = round(facts["apr"] + 5.0, 2)
            fault = "hallucinated_apr"
        if seed == 4 and rng.random() < 0.6:
            # Misread utilization: decision flips on a borderline case.
            cited["utilization"] = max(0, facts["utilization"] - 40)
            decision = decision_rule(cited)
            fault = "misread_utilization"
        explanation = (
            f"Account {case['case_id']}: utilization {cited['utilization']}% on a "
            f"${cited['credit_limit']} limit with balance ${cited['balance']} at "
            f"{cited['apr']}% APR, {cited['months_delinquent']} months delinquent, "
            f"minimum payment ${cited['min_payment']}. Decision: {decision}."
        )
        return {"case_id": case["case_id"], "decision": decision,
                "explanation": explanation, "seed": seed,
                "prompt_variant": prompt_variant, "fault": fault}


class ChallengerModel:
    """Transparent rule challenger: the reference decision rule, no text."""

    name = "challenger-rule-v1"

    def generate(self, case: dict, seed: int = 0, prompt_variant: str = "base") -> dict:
        return {"case_id": case["case_id"],
                "decision": decision_rule(case["facts"]),
                "explanation": "", "seed": seed,
                "prompt_variant": prompt_variant, "fault": None}


class BenchmarkModel:
    """Base-rate benchmark: always the most common ground-truth decision."""

    name = "benchmark-base-rate-v1"

    def __init__(self, cases):
        from collections import Counter
        self.majority = Counter(c["truth"] for c in cases).most_common(1)[0][0]

    def generate(self, case: dict, seed: int = 0, prompt_variant: str = "base") -> dict:
        return {"case_id": case["case_id"], "decision": self.majority,
                "explanation": "", "seed": seed,
                "prompt_variant": prompt_variant, "fault": None}
