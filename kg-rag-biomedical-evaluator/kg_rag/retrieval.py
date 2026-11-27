"""Retrieval: TF-IDF text ranking, graph traversal, and their fusion.

Both retrievers are deterministic and stdlib-only. The TF-IDF ranker is a
stand-in for a dense embedding retriever; the fusion step is the same
shape a hybrid retriever would use, so a real embedding model plugs in
behind the same `retrieve` interface.
"""

import math
import re
from collections import Counter

from .graph import find_entities

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']*")


def tokenize(text):
    return _TOKEN.findall(text.lower())


class TfidfRanker:
    """Deterministic TF-IDF + cosine similarity over document passages."""

    def __init__(self, documents):
        self.documents = documents
        self._doc_tokens = [tokenize(d["text"]) for d in documents]
        n = len(documents)
        df = Counter()
        for tokens in self._doc_tokens:
            for tok in set(tokens):
                df[tok] += 1
        self._idf = {tok: math.log((n + 1) / (count + 1)) + 1.0
                     for tok, count in df.items()}
        self._vectors = [self._vector(tokens) for tokens in self._doc_tokens]

    def _vector(self, tokens):
        counts = Counter(tokens)
        vec = {tok: (count / len(tokens)) * self._idf.get(tok, 1.0)
               for tok, count in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {tok: v / norm for tok, v in vec.items()}

    def score(self, query):
        qvec = self._vector(tokenize(query))
        scored = []
        for doc, dvec in zip(self.documents, self._vectors):
            sim = sum(qvec.get(tok, 0.0) * dvec.get(tok, 0.0) for tok in qvec)
            scored.append((sim, doc["id"]))
        return sorted(scored, reverse=True)

    def top_k(self, query, k=3):
        return [doc_id for _, doc_id in self.score(query)[:k] if _ > 0]


def graph_retrieve(graph, query, hops=2):
    """Documents supporting the entities in the question, via graph walks.

    Returns [(doc_id, weight)] sorted by accumulated edge weight: a document
    is evidence for a question when a graph edge from the question's
    entities is sourced from it. Two hops recover the second link of a
    chain (drug -> gene -> disease) that text ranking alone misses.
    """
    entities = find_entities(query)
    if not entities:
        return []
    # Walk from every entity in the question and union the edges.
    all_edges = []
    for ent in entities:
        _, edges = graph.neighbours(ent, hops=hops)
        all_edges.extend(edges)
    weights = Counter()
    for edge in all_edges:
        weights[edge["source"]] += edge["weight"]
    return sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))


def retrieve(graph, ranker, query, k=3):
    """Fused retrieval: graph evidence first, then TF-IDF text ranking.

    Graph-supported documents rank ahead of text-only matches, because a
    graph edge is a typed relation between the question's entities, while a
    text match may only share a word. Within each group, order is by the
    underlying score.
    """
    graph_docs = [doc_id for doc_id, _ in graph_retrieve(graph, query)]
    text_docs = ranker.top_k(query, k=len(ranker.documents))
    fused = []
    for doc_id in graph_docs:
        if doc_id not in fused:
            fused.append(doc_id)
    for doc_id in text_docs:
        if doc_id not in fused:
            fused.append(doc_id)
    return fused[:k]
