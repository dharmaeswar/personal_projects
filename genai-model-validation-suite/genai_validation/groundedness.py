"""Hallucination and groundedness checks for generated explanations.

Every number an explanation cites must appear in the source facts.
A cited number with no matching source fact is a hallucination.
"""
from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def cited_numbers(text: str) -> list[float]:
    return [float(m) for m in _NUMBER_RE.findall(text)]


def groundedness(explanation: str, facts: dict) -> dict:
    """Score how many cited numbers are grounded in the source facts."""
    # Case ids (e.g. "C010") are identifiers, not cited facts: strip them
    # before extracting numbers so "010" is never scored as a figure.
    text = re.sub(r"\bC\d+\b", "", explanation)
    cited = cited_numbers(text)
    source_values = {float(v) for v in facts.values()}
    # Case ids (e.g. C001 -> 001) are identifiers, not cited facts.
    grounded = 0
    hallucinated = []
    for value in cited:
        if value in source_values:
            grounded += 1
        else:
            hallucinated.append(value)
    total = len(cited)
    score = grounded / total if total else 1.0
    return {"cited": total, "grounded": grounded,
            "hallucinated": hallucinated, "score": round(score, 4),
            "hallucination": bool(hallucinated)}


def hallucination_rate(results: list[dict]) -> dict:
    """Aggregate hallucination rate across per-case groundedness results."""
    flagged = sum(1 for r in results if r["hallucination"])
    total = len(results)
    return {"cases": total, "flagged": flagged,
            "rate": round(flagged / total, 4) if total else 0.0}
