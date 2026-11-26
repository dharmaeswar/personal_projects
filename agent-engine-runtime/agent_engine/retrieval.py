"""Retrieval layer: a small token-overlap index over tools and knowledge.

Agents need to find the right tool and the right knowledge before they
act. KnowledgeIndex stores documents (tool descriptions, runbooks, FAQ
entries) and ranks them for a query by shared-token count with a length
penalty, so a short, on-topic document beats a long, loosely related one.
It is deliberately simple and deterministic: no embeddings, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class Document:
    doc_id: str
    text: str
    kind: str = "knowledge"  # "tool" | "knowledge" | "runbook"
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class SearchHit:
    document: Document
    score: float


class KnowledgeIndex:
    """In-memory retrieval index with deterministic ranking."""

    def __init__(self):
        self._docs: Dict[str, Document] = {}

    def add(self, doc: Document) -> None:
        self._docs[doc.doc_id] = doc

    def remove(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None

    def search(self, query: str, top_k: int = 3,
               kind: str | None = None) -> List[SearchHit]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        hits: List[SearchHit] = []
        for doc in self._docs.values():
            if kind is not None and doc.kind != kind:
                continue
            doc_tokens = _tokens(doc.text)
            overlap = len(query_tokens & doc_tokens)
            if overlap == 0:
                continue
            # Length penalty: prefer the document that says the most about
            # the query in the fewest words (word count, not unique tokens).
            score = overlap / (1.0 + 0.05 * len(doc.text.split()))
            hits.append(SearchHit(document=doc, score=score))
        hits.sort(key=lambda h: (-h.score, h.document.doc_id))
        return hits[:top_k]

    def __len__(self) -> int:
        return len(self._docs)
