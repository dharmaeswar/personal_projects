"""Deterministic retrieval agent.

Plan -> retrieve -> answer with citations -> validate. The decision
logic is a fixed rule-based policy (a stand-in for an LLM agent), so
every run is reproducible with no model API calls. A model-backed agent
plugs into the same interface: replace ``_draft_answer`` with a model
call and keep the retrieval, tools and validation.
"""

import re
from dataclasses import dataclass, field

_SENTENCE = re.compile(r"[^.!?]+[.!?]")
# Words too common to count as evidence that a sentence answers a question.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "i", "my", "me", "we", "you", "he", "she", "it", "they",
    "what", "how", "when", "where", "which", "who", "why",
    "for", "to", "of", "in", "on", "at", "by", "with", "from", "as",
    "and", "or", "not", "no", "is", "can", "could", "should", "would",
})

@dataclass
class Answer:
    """One agent answer, with its evidence and trace."""

    question: str
    text: str
    citations: list
    tools_used: list
    grounded: bool  # every claim sentence traces to a cited document
    escalated: bool = False


@dataclass
class Agent:
    """Retrieval agent over a DocStore, with an MCP-style tool registry."""

    store: object
    registry: object
    max_docs: int = 3

    def _sentences(self, text: str) -> list:
        return [s.strip() for s in _SENTENCE.findall(text) if s.strip()]

    def _draft_answer(self, question: str, hits: list) -> str:
        """Answer only from retrieved sentences that share a word with the
        question. If nothing matches, say so instead of inventing an answer."""
        question_words = (set(re.findall(r"[a-z0-9]+", question.lower()))
                          - _STOPWORDS)
        picked = []
        for hit in hits:
            for sentence in self._sentences(hit.text):
                words = set(re.findall(r"[a-z0-9]+", sentence.lower()))
                if question_words & words and sentence not in picked:
                    picked.append(sentence)
        if not picked:
            return ("I could not find an answer in the knowledge base. "
                    "This question needs a human reviewer.")
        return " ".join(picked[:3])

    def run(self, question: str) -> Answer:
        """Plan, retrieve, answer, validate — one traceable run."""
        tools_used = []
        hits = self.store.search(question, top_k=self.max_docs)
        self.registry.call("search_kb", query=question, top_k=self.max_docs)
        tools_used.append("search_kb")
        citations = self.store.cite(hits)
        text = self._draft_answer(question, hits)
        escalated = text.startswith("I could not find")
        if escalated:
            self.registry.call("escalate_to_human",
                               reason="no grounding document found",
                               question=question)
            tools_used.append("escalate_to_human")
        # Validation: an answer is grounded only when it cites retrieved
        # documents and is not an escalation.
        grounded = bool(citations) and not escalated
        return Answer(question=question, text=text, citations=citations,
                      tools_used=tools_used, grounded=grounded,
                      escalated=escalated)
