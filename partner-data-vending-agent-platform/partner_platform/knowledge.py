"""Knowledge base over unstructured partner content.

Partner documentation arrives as plain text (guides, policy notes, API
references). The knowledge base chunks each document into short passages,
indexes them by keyword, and answers a question with the best-matching
passages plus citations, so an agent never answers from memory alone. Every
passage carries its source document and a freshness date; stale passages are
flagged, not silently served.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "how", "do", "does", "can", "i", "we", "you", "it", "this",
    "that", "by", "from", "as", "at", "be", "our", "your", "what", "when",
}


def _tokens(text: str) -> list:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


@dataclass
class Passage:
    """One chunk of one source document, citable by an agent."""

    doc_id: str
    doc_title: str
    chunk_id: int
    text: str
    fresh_until: str  # ISO date; passages past this date are stale

    def keywords(self) -> set:
        return set(_tokens(self.text))


@dataclass
class Citation:
    """A retrieved passage, scored against the question."""

    passage: Passage
    score: int
    stale: bool


class KnowledgeBase:
    """Chunked, keyword-indexed store of partner documents."""

    def __init__(self) -> None:
        self._passages: list[Passage] = []

    def add_document(self, doc_id: str, title: str, text: str, fresh_until: str,
                     chunk_chars: int = 400) -> int:
        """Split a document into passages and index them. Returns passage count."""
        if not text.strip():
            raise ValueError("document text must not be empty")
        if chunk_chars < 100:
            raise ValueError("chunk_chars must be at least 100")
        count = 0
        for start in range(0, len(text), chunk_chars):
            chunk = text[start:start + chunk_chars].strip()
            if not chunk:
                continue
            self._passages.append(Passage(doc_id, title, count, chunk, fresh_until))
            count += 1
        return count

    def passage_count(self) -> int:
        return len(self._passages)

    def retrieve(self, question: str, top_k: int = 3, today: str = "2026-11-21") -> list[Citation]:
        """Return the best-matching passages for a question, with citations."""
        query_terms = set(_tokens(question))
        if not query_terms:
            return []
        scored = []
        for passage in self._passages:
            overlap = len(query_terms & passage.keywords())
            if overlap:
                scored.append(Citation(passage, overlap, passage.fresh_until < today))
        scored.sort(key=lambda c: (-c.score, c.passage.doc_id, c.passage.chunk_id))
        return scored[:top_k]

    def stale_count(self, today: str = "2026-11-21") -> int:
        return sum(1 for p in self._passages if p.fresh_until < today)
