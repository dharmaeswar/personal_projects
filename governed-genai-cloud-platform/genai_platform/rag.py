"""Retrieval-augmented generation over the platform knowledge base.

Documents are seeded bank policy and runbook text (synthetic, invented).
Retrieval is TF-IDF over word tokens with a character budget and citation
tracking: every answer cites the document and chunk it came from, and a
question with no supporting chunk says so instead of guessing. This is
the retrieval layer the LangChain/LangGraph orchestration calls; a vector
store (for example Amazon Bedrock Knowledge Bases) plugs into the same
``retrieve`` interface.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class Chunk:
    doc_id: str
    title: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.doc_id} :: {self.title}"


@dataclass
class KnowledgeBase:
    chunks: list[Chunk] = field(default_factory=list)

    def add_document(self, doc_id: str, title: str, text: str) -> None:
        """Split a document into sentence chunks of at most ~400 chars."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) + 1 > 400:
                self.chunks.append(Chunk(doc_id, title, current))
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            self.chunks.append(Chunk(doc_id, title, current))

    def _idf(self) -> dict[str, float]:
        doc_count = len(self.chunks) or 1
        df: dict[str, int] = {}
        for chunk in self.chunks:
            for token in set(tokenize(chunk.text)):
                df[token] = df.get(token, 0) + 1
        return {
            token: math.log((doc_count + 1) / (count + 1)) + 1.0
            for token, count in df.items()
        }

    def retrieve(self, question: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        """Rank chunks by TF-IDF overlap with the question. Returns
        (chunk, score) pairs, best first, with zero-overlap chunks dropped."""
        idf = self._idf()
        query_tokens = tokenize(question)
        scored: list[tuple[Chunk, float]] = []
        for chunk in self.chunks:
            tokens = tokenize(chunk.text)
            if not tokens:
                continue
            score = 0.0
            for token in set(query_tokens):
                tf = tokens.count(token) / len(tokens)
                score += tf * idf.get(token, 1.0)
            if score > 0:
                scored.append((chunk, round(score, 4)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def pack_context(
        self, question: str, top_k: int = 3, char_budget: int = 2000
    ) -> tuple[str, list[str]]:
        """Pack the best chunks into a character budget, citations kept.
        Returns (context text, citation list)."""
        parts: list[str] = []
        citations: list[str] = []
        used = 0
        for chunk, _score in self.retrieve(question, top_k=top_k):
            piece = f"[{chunk.citation}] {chunk.text}"
            if used + len(piece) > char_budget and parts:
                break
            parts.append(piece)
            citations.append(chunk.citation)
            used += len(piece)
        return "\n".join(parts), citations


def demo_knowledge_base() -> KnowledgeBase:
    """Seeded synthetic bank policy/runbook documents (invented text)."""
    kb = KnowledgeBase()
    kb.add_document(
        "POL-101",
        "Commercial Lending Policy",
        "Commercial loans above $5 million require two approvals: the "
        "relationship manager and a credit officer. The leverage covenant "
        "limit is 3.5x debt to EBITDA, tested quarterly on borrower "
        "financial statements. A breach triggers a cure period of 30 days "
        "before the loan is classified as non-performing.",
    )
    kb.add_document(
        "RUN-204",
        "Treasury Operations Runbook",
        "Treasury wires above $250,000 need dual authorization in the "
        "payments system. End-of-day liquidity is reported by 6pm Central "
        "and reconciled against the Federal Reserve account. Any variance "
        "above $1 million is escalated to the treasurer the same day.",
    )
    kb.add_document(
        "MRG-310",
        "Model Risk Guidance Summary",
        "Generative AI models used in credit decisions are classified as "
        "high risk and need annual validation. Every model output that "
        "affects a customer must carry a human review step before it is "
        "sent. Prompt injection tests run quarterly and results go to the "
        "model risk committee.",
    )
    kb.add_document(
        "SEC-118",
        "Cloud Security Standard",
        "Production data stores must be encrypted at rest and block public "
        "access. IAM roles follow least privilege: no wildcard actions and "
        "no standing access to production data. Secrets live in the vault, "
        "never in code or environment files. Agent tools run with the "
        "minimum permissions their task needs.",
    )
    return kb
