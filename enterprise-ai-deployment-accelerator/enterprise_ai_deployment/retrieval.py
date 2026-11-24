"""Retrieval over the customer's own documents.

A small in-memory document store with keyword retrieval. Every retrieved
passage carries its document id so answers can cite exactly what they
used — grounding is the enterprise requirement that separates a demo
from a production system.
"""

import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return set(_WORD.findall(text.lower()))


@dataclass
class Document:
    """One enterprise document (policy, runbook, FAQ, contract clause)."""

    doc_id: str
    title: str
    text: str


@dataclass
class RetrievalHit:
    doc_id: str
    title: str
    text: str
    score: float


@dataclass
class DocStore:
    """Keyword document store. Deterministic: ties break by doc_id."""

    docs: list = field(default_factory=list)

    def add(self, doc: Document) -> None:
        if any(d.doc_id == doc.doc_id for d in self.docs):
            raise ValueError(f"duplicate doc_id: {doc.doc_id}")
        self.docs.append(doc)

    def search(self, query: str, top_k: int = 3) -> list:
        """Rank docs by token overlap with the query."""
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored = []
        for doc in self.docs:
            overlap = len(query_tokens & _tokens(doc.title + " " + doc.text))
            if overlap:
                scored.append(RetrievalHit(doc.doc_id, doc.title, doc.text,
                                            overlap / len(query_tokens)))
        scored.sort(key=lambda h: (-h.score, h.doc_id))
        return scored[:top_k]

    def cite(self, hits: list) -> list:
        """Citation strings for the retrieved hits, in rank order."""
        return [f"[{h.doc_id}] {h.title}" for h in hits]
