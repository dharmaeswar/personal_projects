"""Compliance guardrails for research-assistant answers (rule-based checks)."""

import re
from dataclasses import dataclass, field

# Language that must never appear in a research-grade answer.
GUARANTEE_PATTERNS = [
    re.compile(r"\bguarantee[sd]?\b", re.I),
    re.compile(r"\bwill (definitely|certainly) (rise|increase|grow|double)\b", re.I),
    re.compile(r"\bsure (thing|bet|winner)\b", re.I),
]

RECOMMENDATION_PATTERNS = [
    re.compile(r"\b(you should )?(buy|sell|short) (shares|the stock|this stock)\b", re.I),
    re.compile(r"\bstrong buy\b", re.I),
    re.compile(r"\bstrong sell\b", re.I),
]

# Markers that a passage may contain material non-public information.
MNPI_MARKERS = [
    re.compile(r"\bconfidential\b", re.I),
    re.compile(r"\bnon-public\b", re.I),
    re.compile(r"\bdo not (share|distribute|forward)\b", re.I),
    re.compile(r"\binsider\b", re.I),
]

MAX_ANSWER_CHARS = 1200


@dataclass
class GuardrailVerdict:
    passed: bool
    violations: list = field(default_factory=list)


def check_answer(answer_text, citations, source_texts):
    """Check a composed answer. Returns a GuardrailVerdict."""
    violations = []
    if not citations:
        violations.append("no citations attached to the answer")
    for pattern in GUARANTEE_PATTERNS:
        if pattern.search(answer_text):
            violations.append("forward-looking guarantee language")
            break
    for pattern in RECOMMENDATION_PATTERNS:
        if pattern.search(answer_text):
            violations.append("buy/sell recommendation language")
            break
    if len(answer_text) > MAX_ANSWER_CHARS:
        violations.append("answer exceeds 1200 characters")
    for source in source_texts:
        for pattern in MNPI_MARKERS:
            if pattern.search(source):
                violations.append("source passage carries an MNPI marker")
                break
    return GuardrailVerdict(passed=not violations, violations=violations)
