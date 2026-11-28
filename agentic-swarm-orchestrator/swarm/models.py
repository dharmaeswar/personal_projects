"""Simulated model profiles and routing.

No live LLM calls: each profile is a cost/latency/accuracy contract, and a
deterministic hash decides whether a given model finds a given document for a
given question. That makes every agent's behaviour reproducible and lets the
orchestrator measure cost, latency, and yield honestly at demo scale.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


def _draw(*parts: str) -> float:
    """Deterministic uniform draw in [0, 1) from the given key parts."""
    key = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass(frozen=True)
class ModelProfile:
    name: str
    cost_per_doc: float      # simulated dollars per document scanned
    latency_per_doc: float   # simulated seconds per document scanned
    recall: float            # P(agent returns a true answer doc)
    false_positive_rate: float  # P(agent returns a non-answer doc)
    verify_recall: float = 0.97      # P(verification keeps a true positive)
    verify_fp_reject: float = 0.90   # P(verification drops a false positive)


SCOUT = ModelProfile(
    name="scout-small", cost_per_doc=0.002, latency_per_doc=0.010,
    recall=0.62, false_positive_rate=0.08,
)
STANDARD = ModelProfile(
    name="standard", cost_per_doc=0.010, latency_per_doc=0.040,
    recall=0.85, false_positive_rate=0.03,
)
REASONER = ModelProfile(
    name="reasoner-large", cost_per_doc=0.050, latency_per_doc=0.150,
    recall=0.96, false_positive_rate=0.01,
)

PROFILES = {"scout-small": SCOUT, "standard": STANDARD, "reasoner-large": REASONER}


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    score: float
    model: str


def scan_document(model: ModelProfile, doc_id: str, question_id: str,
                  is_answer: bool) -> Candidate | None:
    """Simulate one agent reading one document for one question.

    Returns a candidate when the model flags the document, else None.
    True answers are flagged with probability ``recall``; non-answers are
    flagged with probability ``false_positive_rate``. Scores separate the
    two cases only roughly, so ranking alone cannot replace verification.
    """
    draw = _draw("scan", model.name, doc_id, question_id)
    if is_answer:
        if draw >= model.recall:
            return None
        score = 0.60 + 0.40 * _draw("score", model.name, doc_id, question_id)
    else:
        if draw >= model.false_positive_rate:
            return None
        score = 0.30 + 0.40 * _draw("score", model.name, doc_id, question_id)
    return Candidate(doc_id=doc_id, score=score, model=model.name)


def route(question_complexity: float, budget_per_doc: float) -> ModelProfile:
    """Pick the cheapest model that fits the budget for this step.

    Routing rule: a simple question (complexity < 0.4) goes to the scout;
    a mid question goes to standard; only a hard question (or a generous
    budget) earns the reasoner. The budget cap is a hard constraint: never
    return a model whose cost exceeds it.
    """
    if question_complexity >= 0.7 and REASONER.cost_per_doc <= budget_per_doc:
        return REASONER
    if question_complexity >= 0.4 and STANDARD.cost_per_doc <= budget_per_doc:
        return STANDARD
    if SCOUT.cost_per_doc <= budget_per_doc:
        return SCOUT
    return SCOUT  # cheapest available; caller enforces the budget elsewhere
