"""Deterministic TF-IDF keyword retrieval over research-note chunks (stdlib only)."""

import math
import re
from dataclasses import dataclass

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "is", "was", "are", "were", "it", "its", "as", "at", "from", "that", "this",
    "up", "down", "per", "year", "quarter", "million", "billion", "percent",
    "what", "how", "did", "do", "does", "when", "which", "who", "about",
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def tokenize(text):
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOPWORDS]


@dataclass(frozen=True)
class RetrievalResult:
    chunk: object
    score: float


class Retriever:
    """TF-IDF retriever built once over a fixed chunk list."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.n_docs = len(self.chunks)
        self._doc_freq = {}
        self._chunk_tf = []
        for chunk in self.chunks:
            tokens = tokenize(chunk.text)
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self._chunk_tf.append(tf)
            for token in set(tokens):
                self._doc_freq[token] = self._doc_freq.get(token, 0) + 1

    def _idf(self, token):
        df = self._doc_freq.get(token, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + self.n_docs / df)

    def retrieve(self, query, top_k=5):
        """Return the top_k chunks ranked by TF-IDF cosine-ish score."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        qtf = {}
        for token in query_tokens:
            qtf[token] = qtf.get(token, 0) + 1
        scored = []
        for chunk, tf in zip(self.chunks, self._chunk_tf):
            score = 0.0
            for token, qcount in qtf.items():
                if token in tf:
                    score += qcount * tf[token] * self._idf(token)
            # Normalize by chunk length so long passages do not dominate.
            length = sum(tf.values()) or 1
            score = score / math.sqrt(length)
            if score > 0:
                scored.append(RetrievalResult(chunk=chunk, score=score))
        scored.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return scored[:top_k]
