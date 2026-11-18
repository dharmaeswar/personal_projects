"""Deterministic TF-IDF retrieval over chunks, plus precision/recall.

This is a transparent baseline ranker (plain Python, no model downloads):
it measures how well each *chunking strategy* preserves retrievable
meaning, not how good a neural embedding model is. A real embedding model
can replace :func:`embed` without changing the evaluation harness.
"""

import math
import re

TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return TOKEN.findall(text.lower())


def build_index(chunks):
    """Return (vocab, idf): token -> column, token -> inverse document freq."""
    doc_freq = {}
    for chunk in chunks:
        for token in set(tokenize(chunk["text"])):
            doc_freq[token] = doc_freq.get(token, 0) + 1
    n = max(len(chunks), 1)
    idf = {t: math.log((n + 1) / (df + 1)) + 1.0 for t, df in doc_freq.items()}
    vocab = {token: i for i, token in enumerate(sorted(idf))}
    return vocab, idf


def embed(text, vocab, idf):
    """TF-IDF vector as a sparse dict {column: weight}, L2-normalised."""
    counts = {}
    for token in tokenize(text):
        if token in vocab:
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return {}
    vec = {vocab[token]: count * idf[token] for token, count in counts.items()}
    norm = math.sqrt(sum(w * w for w in vec.values()))
    return {col: w / norm for col, w in vec.items()}


def cosine(vec_a, vec_b):
    """Cosine similarity of two sparse normalised vectors; 0.0 when empty."""
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(w * vec_b.get(col, 0.0) for col, w in vec_a.items())


def search(query, chunks, vocab, idf, k=3):
    """Top-``k`` chunks for ``query`` as (chunk, score) pairs, best first.

    Ties break by chunk order, so results are deterministic.
    """
    query_vec = embed(query, vocab, idf)
    scored = [
        (cosine(query_vec, embed(chunk["text"], vocab, idf)), i, chunk)
        for i, chunk in enumerate(chunks)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [(chunk, score) for score, _, chunk in scored[:k]]


def precision_at_k(retrieved_doc_ids, relevant_doc_ids, k):
    """Relevant docs among the retrieved docs, over min(k, retrieved)."""
    if not retrieved_doc_ids:
        return 0.0
    hits = len(set(retrieved_doc_ids) & set(relevant_doc_ids))
    return hits / min(k, len(retrieved_doc_ids))


def recall_at_k(retrieved_doc_ids, relevant_doc_ids):
    """Relevant docs among the retrieved docs, over all relevant docs."""
    if not relevant_doc_ids:
        return 0.0
    hits = len(set(retrieved_doc_ids) & set(relevant_doc_ids))
    return hits / len(relevant_doc_ids)
