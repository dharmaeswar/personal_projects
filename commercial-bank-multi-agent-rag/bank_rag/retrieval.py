"""Hybrid retrieval over the corpus: TF-IDF text search plus an exact
numeric-table lookup for borrower figures.

No embeddings or model downloads: the ranker is a deterministic TF-IDF
baseline, and the numeric lookup reads the figures table directly. A real
embedding model and vector database can replace `score_text` without
changing the pipeline interface.
"""

import math
import re
from collections import Counter

from .corpus import BORROWERS

TOKEN_RE = re.compile(r"[a-z0-9]+")

METRIC_KEYWORDS = {
    "revenue": ["revenue", "sales", "turnover"],
    "ebitda": ["ebitda", "earnings"],
    "total_debt": ["debt", "leverage", "borrowings"],
    "cash": ["cash"],
    "interest_expense": ["interest expense", "interest"],
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
    "for", "and", "or", "with", "what", "which", "does", "do", "how",
    "by", "at", "its", "it", "this", "that",
}


def tokenize(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class TextIndex:
    """TF-IDF index over corpus documents, built once and reused."""

    def __init__(self, docs):
        self.docs = docs
        self.doc_tokens = [tokenize(d["text"]) for d in docs]
        self.doc_freq = Counter()
        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.doc_freq[token] += 1
        self.n_docs = len(docs)

    def idf(self, token):
        return math.log((1 + self.n_docs) / (1 + self.doc_freq.get(token, 0))) + 1.0

    def score(self, query):
        query_tokens = tokenize(query)
        scores = []
        for i, tokens in enumerate(self.doc_tokens):
            counts = Counter(tokens)
            total = len(tokens) or 1
            score = 0.0
            for token in set(query_tokens):
                if token in counts:
                    tf = counts[token] / total
                    score += tf * self.idf(token)
            scores.append((score, self.docs[i]))
        scores.sort(key=lambda item: item[0], reverse=True)
        return scores


def find_borrower(question):
    """Return the borrower named in the question, or None."""
    lowered = question.lower()
    for name in BORROWERS:
        if name.lower() in lowered:
            return name
    return None


def numeric_lookup(question):
    """Exact lookup of borrower figures named in the question.

    Ratio questions also pull the operands the ratio needs, so the
    analyst can compute from retrieved evidence alone.

    Returns a list of retrieved facts: {doc_id, kind, text, value}.
    """
    borrower = find_borrower(question)
    lowered = question.lower()
    if borrower is None:
        # Comparison questions name no borrower: pull the matched metrics
        # for every borrower so the analyst can compare from evidence.
        if any(w in lowered for w in ("highest", "lowest", "which", "compare")):
            metrics = set()
            for metric, keywords in METRIC_KEYWORDS.items():
                if any(kw in lowered for kw in keywords):
                    metrics.add(metric)
            if "margin" in lowered:
                metrics.update({"ebitda", "revenue"})
            if "leverage" in lowered:
                metrics.update({"total_debt", "ebitda"})
            facts = []
            for name in BORROWERS:
                for metric in sorted(metrics):
                    facts.append({
                        "doc_id": f"{name}|financials",
                        "borrower": name,
                        "kind": "financials",
                        "metric": metric,
                        "value": BORROWERS[name][metric],
                        "text": f"{name} reported {metric.replace('_', ' ')} of "
                                f"{BORROWERS[name][metric]:.1f} million dollars.",
                    })
            return facts
        return []
    lowered = question.lower()
    figures = BORROWERS[borrower]
    metrics = set()
    for metric, keywords in METRIC_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            metrics.add(metric)
    if "leverage" in lowered:
        metrics.update({"total_debt", "ebitda"})
    if "coverage" in lowered:
        metrics.update({"ebitda", "interest_expense"})
    if "margin" in lowered:
        metrics.update({"ebitda", "revenue"})
    if any(w in lowered for w in ("covenant", "compliance", "breach")):
        # A covenant check needs every figure: leverage and coverage.
        metrics.update({"revenue", "ebitda", "total_debt", "cash",
                        "interest_expense"})
    facts = []
    for metric in sorted(metrics):
        facts.append({
            "doc_id": f"{borrower}|financials",
            "borrower": borrower,
            "kind": "financials",
            "metric": metric,
            "value": figures[metric],
            "text": f"{borrower} reported {metric.replace('_', ' ')} of "
                    f"{figures[metric]:.1f} million dollars.",
        })
    return facts


def hybrid_retrieve(question, docs, index, k=3):
    """Combine TF-IDF text ranking with the numeric lookup.

    Numeric facts always rank first (they are exact) and are never cut
    by the text cap; the cap applies to text hits only. The context
    budget in `build_context` still bounds what the analyst sees.
    """
    results = []
    seen = set()
    for fact in numeric_lookup(question):
        results.append({"doc_id": fact["doc_id"], "borrower": fact["borrower"],
                        "kind": fact["kind"], "text": fact["text"],
                        "score": 1.0, "source": "numeric-table"})
        seen.add(fact["doc_id"])
    text_added = 0
    for score, doc in index.score(question):
        if score <= 0:
            continue
        if doc["doc_id"] in seen:
            continue
        results.append({"doc_id": doc["doc_id"], "borrower": doc["borrower"],
                        "kind": doc["kind"], "text": doc["text"],
                        "score": round(score, 4), "source": "text-search"})
        seen.add(doc["doc_id"])
        text_added += 1
        if text_added >= k:
            break
    return results
