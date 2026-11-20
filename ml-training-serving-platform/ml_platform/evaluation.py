"""Experiment tracking, model evaluation harness, and retrieval evaluation.

This is the experimentation layer a Central AI-style team runs on top of the
training/serving platform: every training run is logged with its
hyperparameters and metrics, candidate model versions are evaluated on a
held-out set and compared against production with a promotion gate, and a
small keyword ranker is evaluated with precision@k / MRR for the
search-and-knowledge-discovery use case (synthetic docs and queries only).
"""

import hashlib
import json
import math
import os
import random
import re
import time

from .training import evaluate

# ---------------------------------------------------------------------------
# Experiment tracking
# ---------------------------------------------------------------------------


def log_experiment(path, name, hyperparams, metrics, model_version=None,
                   dataset=None):
    """Append one experiment run to a JSONL log. Returns the run record."""
    record = {
        "name": name,
        "hyperparams": dict(hyperparams),
        "metrics": dict(metrics),
        "model_version": model_version,
        "dataset": dataset,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def list_experiments(path):
    """Read all logged runs; returns [] when the log does not exist yet."""
    if not os.path.exists(path):
        return []
    runs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def best_experiment(path, metric="auc"):
    """Return the run with the highest value of `metric`, or None."""
    runs = list_experiments(path)
    scored = [r for r in runs if metric in r.get("metrics", {})]
    if not scored:
        return None
    return max(scored, key=lambda r: r["metrics"][metric])


# ---------------------------------------------------------------------------
# Model evaluation harness + promotion gate
# ---------------------------------------------------------------------------


def evaluate_version(model, eval_rows):
    """Evaluate one model version on held-out rows (accuracy/precision/recall/AUC)."""
    return evaluate(model, eval_rows)


def dataset_fingerprint(rows):
    """Stable hash of an eval set, so runs are comparable only on same data."""
    blob = json.dumps(
        [[r[0], r[1]] for r in rows], sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def compare_versions(candidate_metrics, production_metrics, primary="auc",
                     min_improvement=0.0, floors=None):
    """Compare a candidate against production.

    Returns a verdict dict: promote (bool), primary_delta, and reasons.
    The candidate promotes when it beats production on `primary` by at
    least `min_improvement` and clears every floor in `floors`
    (e.g. {"accuracy": 0.70, "recall": 0.50}).
    """
    floors = floors or {}
    reasons = []
    primary_delta = round(
        candidate_metrics.get(primary, 0.0) - production_metrics.get(primary, 0.0), 4
    )
    promote = True
    if primary_delta < min_improvement:
        promote = False
        reasons.append(
            f"{primary} delta {primary_delta} below required {min_improvement}"
        )
    for metric, floor in floors.items():
        value = candidate_metrics.get(metric)
        if value is None:
            promote = False
            reasons.append(f"{metric} missing from candidate metrics")
        elif value < floor:
            promote = False
            reasons.append(f"{metric} {value} below floor {floor}")
    if promote:
        reasons.append(f"{primary} improved by {primary_delta}; all floors met")
    return {"promote": promote, "primary_delta": primary_delta, "reasons": reasons}


def promotion_gate(candidate_model, production_model, eval_rows, primary="auc",
                   min_improvement=0.005, floors=None):
    """End-to-end gate: evaluate both versions on the same held-out set."""
    fingerprint = dataset_fingerprint(eval_rows)
    candidate = evaluate_version(candidate_model, eval_rows)
    production = evaluate_version(production_model, eval_rows)
    verdict = compare_versions(candidate, production, primary=primary,
                               min_improvement=min_improvement, floors=floors)
    verdict["candidate"] = candidate
    verdict["production"] = production
    verdict["dataset_fingerprint"] = fingerprint
    return verdict


# ---------------------------------------------------------------------------
# Retrieval evaluation (search / knowledge discovery)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text):
    return _TOKEN.findall(text.lower())


def rank_documents(query, docs):
    """Rank docs by query-term overlap (title terms count double).

    `docs` is a list of {"id": str, "title": str, "text": str}.
    Returns doc ids ordered best-first; ties break by doc id for stability.
    """
    query_terms = set(_tokens(query))
    scored = []
    for doc in docs:
        title_terms = _tokens(doc["title"])
        text_terms = _tokens(doc["text"])
        score = 2 * sum(1 for t in title_terms if t in query_terms)
        score += sum(1 for t in text_terms if t in query_terms)
        scored.append((-score, doc["id"]))
    scored.sort()
    return [doc_id for _, doc_id in scored]


def precision_at_k(ranked, relevant, k):
    """Fraction of the top-k ranked docs that are relevant."""
    if k <= 0:
        return 0.0
    top = ranked[:k]
    if not top:
        return 0.0
    return round(sum(1 for d in top if d in set(relevant)) / len(top), 4)


def reciprocal_rank(ranked, relevant):
    """1 / rank of the first relevant doc, or 0.0 when none is ranked."""
    relevant = set(relevant)
    for i, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return round(1.0 / i, 4)
    return 0.0


def mean_reciprocal_rank(queries, docs):
    """Mean reciprocal rank over (query, relevant doc ids) pairs."""
    if not queries:
        return 0.0
    scores = [reciprocal_rank(rank_documents(q, docs), rel) for q, rel in queries]
    return round(sum(scores) / len(scores), 4)


_TOPICS = [
    ("deploy pipeline", "How to deploy a machine learning pipeline to production",
     "steps to deploy a machine learning pipeline with canary rollout and rollback"),
    ("model drift", "Detecting model drift in production models",
     "monitor model drift with population stability index and alert on drift"),
    ("feature store", "Building a feature store for training and serving",
     "feature store design for consistent training and serving features"),
    ("experiment tracking", "Tracking machine learning experiments and metrics",
     "log experiment runs with hyperparameters and metrics for comparison"),
    ("llm evaluation", "Evaluating large language model outputs",
     "evaluation harness for large language model responses and benchmarks"),
    ("data validation", "Validating training data before model training",
     "data validation checks for schema drift and missing values"),
]


def generate_search_corpus(seed=11):
    """Synthetic docs + queries with known relevant docs (seeded, reproducible)."""
    rng = random.Random(seed)
    docs = [
        {"id": f"doc-{i:02d}", "title": title, "text": text}
        for i, (_, title, text) in enumerate(_TOPICS)
    ]
    # A few distractor docs on unrelated topics.
    distractors = [
        ("office catering", "Team lunch catering options for the office",
         "weekly lunch menu and catering vendors for the office"),
        ("travel policy", "Travel booking policy for conferences",
         "book travel for conferences under the travel policy"),
    ]
    for j, (_, title, text) in enumerate(distractors):
        docs.append({"id": f"doc-{len(_TOPICS) + j:02d}", "title": title, "text": text})
    rng.shuffle(docs)
    queries = [(topic, [f"doc-{i:02d}"]) for i, (topic, _, _) in enumerate(_TOPICS)]
    return docs, queries


def evaluate_retrieval(docs, queries, k=3):
    """Precision@k and MRR for the keyword ranker on a synthetic corpus."""
    precisions = [
        precision_at_k(rank_documents(q, docs), rel, k) for q, rel in queries
    ]
    return {
        "precision_at_%d" % k: round(sum(precisions) / len(precisions), 4)
        if precisions else 0.0,
        "mrr": mean_reciprocal_rank(queries, docs),
        "n_queries": len(queries),
    }
