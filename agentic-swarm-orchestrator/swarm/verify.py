"""Verification: voting, consensus, and sampling-based quality measurement.

The orchestrator never trusts a single agent's output. Candidates are
re-checked by an independent verification pass (a different model, or a
vote across agents), and quality is measured with precision and recall
against ground truth — plus a sampling estimator for when the full truth
is not available to read.
"""
from __future__ import annotations

import random

from .models import ModelProfile, _draw


def verify_candidate(model: ModelProfile, doc_id: str, question_id: str,
                     is_answer: bool) -> bool:
    """Second-pass check of one candidate. True positives usually survive;
    false positives are usually caught."""
    draw = _draw("verify", model.name, doc_id, question_id)
    if is_answer:
        return draw < model.verify_recall
    return draw >= model.verify_fp_reject


def vote(candidates_by_agent: list[set[str]], min_votes: int = 2) -> set[str]:
    """Consensus: keep a doc only when at least ``min_votes`` agents flagged it."""
    counts: dict[str, int] = {}
    for flagged in candidates_by_agent:
        for doc_id in flagged:
            counts[doc_id] = counts.get(doc_id, 0) + 1
    return {doc_id for doc_id, n in counts.items() if n >= min_votes}


def precision_recall(found: set[str], truth: set[str]) -> tuple[float, float]:
    """(precision, recall) of ``found`` against ``truth``."""
    if not found:
        return 0.0, 0.0
    tp = len(found & truth)
    precision = tp / len(found)
    recall = tp / len(truth) if truth else 0.0
    return precision, recall


def sample_precision(found: list[str], truth: set[str], sample_size: int,
                     seed: int = 7) -> tuple[float, int]:
    """Estimate precision by checking a random sample instead of every result.

    Returns (estimated precision, sample size actually checked). Use this
    when reading every trace is too expensive — the same reason a swarm
    measures quality by sampling rather than by reading all output.
    """
    if not found:
        return 0.0, 0
    rng = random.Random(seed)
    sample = rng.sample(found, min(sample_size, len(found)))
    hits = sum(1 for doc_id in sample if doc_id in truth)
    return hits / len(sample), len(sample)
