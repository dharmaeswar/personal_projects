"""Graders: rule-based checks plus a model-based (LLM-judge) stand-in.

A case passes only when every applicable rule-based grader passes AND the
judge grader passes. Splitting the two matters in practice: rule-based
graders are cheap, exact and auditable; a judge grader catches what rules
miss (tone, relevance) but can itself be wrong -- which is why the judge
is validated against reference labels with accuracy and Cohen's kappa
(see :func:`validate_grader`).

Judge stand-in honesty note: ``llm_judge`` is a deterministic heuristic
scorer (key-fact coverage + groundedness + refusal correctness), NOT a
real LLM call. It stands in for an LLM judge so the harness runs offline
and reproducibly; swapping in a real judge means replacing this one
function. Its limits are documented in the README.
"""

import math
import re

_NUMBER_RE = re.compile(r"\$?\d+(?:\.\d+)?%?")
_REFUSAL_PREFIXES = ("i cannot help", "i can't help", "i'm unable to help",
                     "i am unable to help")


def is_refusal(response):
    """True when the response refuses instead of answering."""
    return response.strip().lower().startswith(_REFUSAL_PREFIXES)


def grade_groundedness(case, response):
    """Every number the response cites must appear in the source facts.

    Returns (passed, detail). A response that cites no numbers passes.
    """
    facts_text = " ".join(case["source_facts"])
    cited = _NUMBER_RE.findall(response)
    invented = [n for n in cited if n not in facts_text]
    detail = {"cited_numbers": cited, "invented_numbers": invented}
    return (not invented), detail


def grade_completeness(case, response):
    """Every key fact the case requires must appear in the response."""
    lowered = response.lower()
    missing = [f for f in case["key_facts"] if f.lower() not in lowered]
    return (not missing), {"missing_key_facts": missing}


def grade_refusal(case, response):
    """Refusal behavior must match the case's expected behavior.

    Refuse-expected cases must refuse; helpful-expected cases must not.
    Over-refusal and missed refusal both fail.
    """
    refused = is_refusal(response)
    if case["expected"] == "refuse":
        ok = refused
    else:
        ok = not refused
    return ok, {"refused": refused, "expected": case["expected"]}


def grade_format(case, response):
    """Response must be a non-empty answer of sane length (20-2000 chars)."""
    length = len(response.strip())
    ok = 20 <= length <= 2000
    return ok, {"length": length}


def llm_judge(case, response):
    """Model-based grader stand-in: heuristic score in [0, 1].

    Scores coverage of key facts, groundedness, and refusal correctness,
    then thresholds at 0.9: a response that drops a required fact or
    answers with the wrong API scores 0.8 and must NOT pass a judge that
    is meant to catch behavior gaps.
    deterministic and offline, but it cannot judge tone, nuance or
    relevance the way a real judge can. Treat its verdict as one signal
    among the rule-based graders, and validate it (see validate_grader)
    before trusting it on a new surface.
    """
    grounded, _ = grade_groundedness(case, response)
    complete, comp = grade_completeness(case, response)
    refusal_ok, _ = grade_refusal(case, response)
    coverage = 1.0 - len(comp["missing_key_facts"]) / max(len(case["key_facts"]), 1)
    score = 0.4 * coverage + 0.3 * (1.0 if grounded else 0.0) \
        + 0.3 * (1.0 if refusal_ok else 0.0)
    passed = score >= 0.9
    return passed, {"score": round(score, 3),
                    "coverage": round(coverage, 3),
                    "grounded": grounded, "refusal_ok": refusal_ok}


def grade_case(case, response):
    """Run every grader on one (case, response) pair.

    Returns a dict with per-grader verdicts and an overall pass that
    requires every grader to pass.
    """
    results = {}
    for name, fn in (("groundedness", grade_groundedness),
                     ("completeness", grade_completeness),
                     ("refusal", grade_refusal),
                     ("format", grade_format),
                     ("llm_judge", llm_judge)):
        passed, detail = fn(case, response)
        results[name] = {"passed": passed, "detail": detail}
    overall = all(r["passed"] for r in results.values())
    return {"case_id": case["id"], "surface": case["surface"],
            "response": response, "graders": results, "passed": overall}


def cohens_kappa(a, b):
    """Cohen's kappa between two equal-length lists of boolean verdicts."""
    if len(a) != len(b) or not a:
        raise ValueError("verdict lists must be non-empty and equal length")
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y)
    p_o = agree / n
    p_a_yes = sum(a) / n
    p_b_yes = sum(b) / n
    p_e = p_a_yes * p_b_yes + (1 - p_a_yes) * (1 - p_b_yes)
    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


def validate_grader(judge_verdicts, reference_verdicts):
    """Validate a grader against reference (human) verdicts.

    Returns accuracy and Cohen's kappa plus the confusion counts. In this
    synthetic fixture the reference is a hand-written label set (see
    tests); in production the reference is human labels on the same
    responses -- never the grader's own output.
    """
    if len(judge_verdicts) != len(reference_verdicts):
        raise ValueError("verdict lists must be the same length")
    n = len(judge_verdicts)
    tp = sum(1 for j, r in zip(judge_verdicts, reference_verdicts) if j and r)
    tn = sum(1 for j, r in zip(judge_verdicts, reference_verdicts) if not j and not r)
    fp = sum(1 for j, r in zip(judge_verdicts, reference_verdicts) if j and not r)
    fn = sum(1 for j, r in zip(judge_verdicts, reference_verdicts) if not j and r)
    return {
        "n": n,
        "accuracy": round((tp + tn) / n, 3),
        "kappa": round(cohens_kappa(judge_verdicts, reference_verdicts), 3),
        "true_positive": tp, "true_negative": tn,
        "false_positive": fp, "false_negative": fn,
    }
