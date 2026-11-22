"""Output-reliability, sensitivity, drift and explainability checks."""
from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9%.]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def reliability(model, cases, seeds=(0, 1, 2, 3, 4)) -> dict:
    """Repeat the same prompt across seeds; measure decision and text stability."""
    per_case = []
    for case in cases:
        runs = [model.generate(case, seed=s) for s in seeds]
        decisions = [r["decision"] for r in runs]
        base = decisions[0]
        decision_agreement = sum(d == base for d in decisions) / len(decisions)
        texts = [r["explanation"] for r in runs]
        sims = [jaccard(texts[0], t) for t in texts[1:]]
        text_stability = sum(sims) / len(sims) if sims else 1.0
        per_case.append({"case_id": case["case_id"],
                         "decision_agreement": round(decision_agreement, 4),
                         "text_stability": round(text_stability, 4)})
    mean_decision = sum(p["decision_agreement"] for p in per_case) / len(per_case)
    mean_text = sum(p["text_stability"] for p in per_case) / len(per_case)
    unstable = sum(1 for p in per_case if p["decision_agreement"] < 1.0)
    return {"cases": len(per_case), "mean_decision_agreement": round(mean_decision, 4),
            "mean_text_stability": round(mean_text, 4),
            "unstable_cases": unstable, "per_case": per_case}


def sensitivity(model, cases, variants=("reordered", "paraphrased")) -> dict:
    """Perturb the prompt without changing the facts; decisions must not flip."""
    flips = 0
    total = 0
    per_variant = {}
    for variant in variants:
        vflips = 0
        for case in cases:
            base = model.generate(case, seed=0, prompt_variant="base")["decision"]
            alt = model.generate(case, seed=0, prompt_variant=variant)["decision"]
            total += 1
            if alt != base:
                flips += 1
                vflips += 1
        per_variant[variant] = {"cases": len(cases), "flips": vflips,
                                "flip_rate": round(vflips / len(cases), 4)}
    return {"cases": total, "flips": flips,
            "flip_rate": round(flips / total, 4) if total else 0.0,
            "per_variant": per_variant}


def psi(expected: list[float], actual: list[float], bins: int = 5) -> float:
    """Population Stability Index between two score distributions."""
    if not expected or not actual:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi == lo:
        return 0.0
    width = (hi - lo) / bins
    total = 0.0
    for i in range(bins):
        a, b = lo + i * width, lo + (i + 1) * width
        e = sum(1 for x in expected if a <= x < b or (i == bins - 1 and x == b))
        c = sum(1 for x in actual if a <= x < b or (i == bins - 1 and x == b))
        e_pct = max(e / len(expected), 0.0001)
        c_pct = max(c / len(actual), 0.0001)
        total += (c_pct - e_pct) * math.log(c_pct / e_pct)
    return round(total, 4)


def explainability(explanation: str, facts: dict, decision_drivers: list[str]) -> dict:
    """Which decision-driving facts does the explanation actually cite?

    ``decision_drivers`` are the fact keys that drove the decision
    (here: utilization and months delinquent). An explanation that
    never names its drivers is not explainable, however fluent it reads.
    """
    text = explanation.lower()
    cited = [k for k in decision_drivers if str(facts[k]) in text]
    coverage = len(cited) / len(decision_drivers) if decision_drivers else 1.0
    return {"drivers": decision_drivers, "cited_drivers": cited,
            "coverage": round(coverage, 4)}
