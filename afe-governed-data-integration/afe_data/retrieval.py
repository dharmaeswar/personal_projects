"""Retrieval for AI systems: search, embeddings-style ranking, feature store.

The AI system never reads raw client tables. It queries a governed index:
documents (position notes + risk memos) are chunked, ranked with TF-IDF
cosine similarity (the same interface a real embeddings store fronts), and
returned with citations and the sensitivity of every field, so the caller
can mask restricted values before they reach a model. A feature-store
snapshot gives the model point-in-time features for a position.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class RetrievedDoc:
    doc_id: str
    score: float
    text: str
    sensitivity: str


class RetrievalIndex:
    """Small in-memory TF-IDF index over governed documents."""

    def __init__(self):
        self.docs: list[dict] = []

    def add(self, doc_id: str, text: str, sensitivity: str = "internal") -> None:
        self.docs.append({"doc_id": doc_id, "text": text, "sensitivity": sensitivity})

    def _idf(self) -> dict[str, float]:
        doc_count = len(self.docs)
        df: dict[str, int] = {}
        for doc in self.docs:
            for token in set(tokenize(doc["text"])):
                df[token] = df.get(token, 0) + 1
        return {t: math.log((1 + doc_count) / (1 + n)) + 1.0 for t, n in df.items()}

    def search(self, query: str, top_k: int = 3) -> list[RetrievedDoc]:
        if not self.docs:
            return []
        idf = self._idf()
        query_tokens = tokenize(query)
        query_vec = {t: query_tokens.count(t) * idf.get(t, 0.0) for t in set(query_tokens)}
        query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1.0
        scored = []
        for doc in self.docs:
            tokens = tokenize(doc["text"])
            doc_vec = {t: tokens.count(t) * idf.get(t, 0.0) for t in set(tokens)}
            doc_norm = math.sqrt(sum(v * v for v in doc_vec.values())) or 1.0
            dot = sum(query_vec.get(t, 0.0) * doc_vec.get(t, 0.0) for t in query_vec)
            scored.append(
                RetrievedDoc(doc["doc_id"], dot / (query_norm * doc_norm), doc["text"], doc["sensitivity"])
            )
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:top_k]


def feature_snapshot(canonical_row: dict) -> dict:
    """Point-in-time features for one position, for the model feature store."""
    notional = canonical_row.get("notional")
    try:
        notional_value = float(notional) if notional is not None else 0.0
    except (TypeError, ValueError):
        notional_value = 0.0
    return {
        "position_id": canonical_row.get("position_id"),
        "client_id": canonical_row.get("client_id"),
        "instrument": canonical_row.get("instrument"),
        "notional": notional_value,
        "notional_bucket": "large" if abs(notional_value) >= 1_000_000 else "small",
        "currency": canonical_row.get("currency"),
        "valuation_date": canonical_row.get("valuation_date"),
        "as_of": canonical_row.get("valuation_date"),
    }
