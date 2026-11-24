"""Deterministic TF-IDF retrieval over the help-center knowledge base.

Returns ranked articles with citations so an agent (or an agent-assist
system) can quote the source it relied on. Plain Python, no vector
database, no model calls — the ranking is reproducible and testable.
"""

import math
import re
from dataclasses import dataclass

from .data import KB_ARTICLES

_TOKEN = re.compile(r"[a-z0-9]+")

# Common words carry no retrieval signal; drop them before scoring.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "can",
    "could", "will", "would", "should", "do", "does", "did", "i", "my",
    "me", "you", "your", "we", "when", "what", "how", "why", "where",
    "to", "of", "in", "on", "at", "for", "and", "or", "it", "its",
    "this", "that", "with", "within", "after", "before", "from", "by",
    "please", "get", "gets",
}


def _tokens(text):
    out = []
    for term in _TOKEN.findall(text.lower()):
        if term in STOPWORDS:
            continue
        # Naive singularisation so "refunds" matches a "refund" query.
        if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
            term = term[:-1]
        out.append(term)
    return out


@dataclass
class RetrievalHit:
    article_id: str
    title: str
    score: float
    snippet: str


class KnowledgeRetriever:
    def __init__(self, articles=None):
        self.articles = list(articles if articles is not None else KB_ARTICLES)
        self._doc_freq = {}
        self._vectors = []
        for article in self.articles:
            terms = _tokens(article.title + " " + article.body)
            counts = {}
            for term in terms:
                counts[term] = counts.get(term, 0) + 1
            for term in counts:
                self._doc_freq[term] = self._doc_freq.get(term, 0) + 1
            self._vectors.append(counts)
        self._n_docs = max(len(self.articles), 1)

    def _idf(self, term):
        return math.log((1 + self._n_docs) / (1 + self._doc_freq.get(term, 0))) + 1.0

    def retrieve(self, query, k=3):
        query_terms = _tokens(query)
        if not query_terms:
            return []
        query_counts = {}
        for term in query_terms:
            query_counts[term] = query_counts.get(term, 0) + 1
        scored = []
        for article, counts in zip(self.articles, self._vectors):
            score = 0.0
            for term, qc in query_counts.items():
                if term in counts:
                    score += qc * counts[term] * self._idf(term) ** 2
            if score > 0:
                norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
                scored.append((score / norm, article))
        scored.sort(key=lambda pair: -pair[0])
        hits = []
        for score, article in scored[:k]:
            snippet = article.body[:160]
            if len(article.body) > 160:
                snippet += "..."
            hits.append(RetrievalHit(article.article_id, article.title,
                                     round(score, 4), snippet))
        return hits
