"""Knowledge layer: retrieval over code, research, and data corpora.

Deterministic TF-IDF-weighted keyword retrieval using only the standard
library. Every returned passage carries its document id, kind, and title so
agents can cite exactly what they used.
"""

import math
import re
from collections import Counter

from .chunking import chunk_corpus

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "it", "its", "by", "at", "as", "be", "that",
    "this", "from", "when", "which", "so", "we", "our", "per", "than", "then",
}


def tokenize(text):
    """Lowercase word tokens with stopwords removed."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS]


class KnowledgeLayer:
    """Indexed passages over the seeded corpora, searchable by keyword."""

    def __init__(self, documents):
        self.chunks = chunk_corpus(documents)
        self._doc_freq = Counter()
        for chunk in self.chunks:
            for token in set(tokenize(chunk["text"])):
                self._doc_freq[token] += 1
        self.n_chunks = len(self.chunks)

    def _idf(self, token):
        return math.log((self.n_chunks + 1) / (self._doc_freq.get(token, 0) + 1)) + 1.0

    def search(self, query, kind=None, top_k=3):
        """Top-k passages for a query, optionally restricted to one kind."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored = []
        for chunk in self.chunks:
            if kind is not None and chunk["kind"] != kind:
                continue
            chunk_tokens = Counter(tokenize(chunk["text"]))
            score = 0.0
            for token in set(query_tokens):
                if token in chunk_tokens:
                    score += chunk_tokens[token] * self._idf(token)
            # Small bonus when the query words appear in the title.
            title_tokens = set(tokenize(chunk["title"]))
            score += 0.5 * len(set(query_tokens) & title_tokens)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["doc_id"], pair[1]["passage_index"]))
        return [
            {"score": round(score, 3), **chunk} for score, chunk in scored[:top_k]
        ]

    def get_passage(self, doc_id, passage_index=0):
        """One passage by document id and index, or None."""
        for chunk in self.chunks:
            if chunk["doc_id"] == doc_id and chunk["passage_index"] == passage_index:
                return chunk
        return None
