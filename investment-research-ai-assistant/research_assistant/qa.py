"""Grounded Q&A: answer only from retrieved passages, with citations."""

import re
import time
from dataclasses import dataclass, field

from .chunking import chunk_corpus
from .corpus import load_corpus
from .guardrails import check_answer
from .observability import log_query
from .retrieval import Retriever, tokenize

MIN_RELEVANCE_SCORE = 0.5


@dataclass
class Answer:
    question: str
    text: str
    citations: list = field(default_factory=list)
    grounded: bool = False
    guardrail_passed: bool = False
    guardrail_violations: list = field(default_factory=list)
    retrieved_ids: list = field(default_factory=list)


def _pick_claim_sentences(chunk_text, query_tokens, max_sentences=3):
    """Pick the sentences in a chunk that share the most tokens with the query."""
    sentences = re.split(r"(?<=[.!?])\s+", chunk_text.strip())
    scored = []
    for sentence in sentences:
        tokens = set(tokenize(sentence))
        overlap = len(tokens & set(query_tokens))
        if overlap > 0:
            scored.append((overlap, sentence))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [s for _, s in scored[:max_sentences]]


class ResearchAssistant:
    """Extractive, grounded research copilot over the seeded corpus."""

    def __init__(self, documents=None, top_k=3):
        self.documents = documents if documents is not None else load_corpus()
        self.chunks = chunk_corpus(self.documents)
        self.retriever = Retriever(self.chunks)
        self.top_k = top_k

    def ask(self, question, log_path=None):
        started = time.time()
        results = self.retriever.retrieve(question, top_k=self.top_k)
        query_tokens = tokenize(question)
        relevant = [r for r in results if r.score >= MIN_RELEVANCE_SCORE]
        retrieved_ids = [r.chunk.chunk_id for r in results]

        if not relevant:
            answer = Answer(
                question=question,
                text="Not covered by the research notes: no retrieved passage is relevant to this question.",
                grounded=True,
                retrieved_ids=retrieved_ids,
            )
        else:
            claims = []
            citations = []
            for result in relevant:
                chunk = result.chunk
                for sentence in _pick_claim_sentences(chunk.text, query_tokens):
                    claims.append(sentence)
                    citations.append(
                        f"{chunk.doc_id} ({chunk.doc_type}, {chunk.date})"
                    )
            text = " ".join(claims)
            verdict = check_answer(text, citations, [r.chunk.text for r in relevant])
            answer = Answer(
                question=question,
                text=text,
                citations=citations,
                grounded=True,
                guardrail_passed=verdict.passed,
                guardrail_violations=verdict.violations,
                retrieved_ids=retrieved_ids,
            )
        if log_path is not None:
            log_query(
                log_path,
                question=question,
                retrieved_ids=retrieved_ids,
                grounded=answer.grounded,
                guardrail_passed=answer.guardrail_passed,
                latency_ms=round((time.time() - started) * 1000, 1),
            )
        return answer
