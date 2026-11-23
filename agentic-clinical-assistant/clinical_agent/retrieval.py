"""Deterministic TF-IDF retrieval over the synthetic knowledge base.

Plain Python only: no model downloads, no API calls, no vector database.
Scores are reproducible, which keeps the eval suite stable.
"""

import math
import re

from .kb import KNOWLEDGE_BASE

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return _TOKEN.findall(text.lower())


def _idf():
    n_docs = len(KNOWLEDGE_BASE)
    doc_freq = {}
    for doc in KNOWLEDGE_BASE:
        for term in set(tokenize(doc["title"] + " " + doc["text"])):
            doc_freq[term] = doc_freq.get(term, 0) + 1
    return {
        term: math.log((1 + n_docs) / (1 + count)) + 1.0
        for term, count in doc_freq.items()
    }


_IDF = _idf()


def search(query, top_k=3):
    """Return the top_k documents for a query as (doc, score) pairs."""
    query_terms = tokenize(query)
    if not query_terms:
        return []
    scored = []
    for doc in KNOWLEDGE_BASE:
        tokens = tokenize(doc["title"] + " " + doc["text"])
        term_freq = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
        score = 0.0
        for term in set(query_terms):
            if term in term_freq:
                score += term_freq[term] * _IDF.get(term, 1.0)
        if score > 0:
            scored.append((doc, round(score, 4)))
    scored.sort(key=lambda pair: (-pair[1], pair[0]["doc_id"]))
    return scored[: max(1, top_k)]
