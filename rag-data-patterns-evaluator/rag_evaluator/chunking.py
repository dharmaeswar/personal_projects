"""Chunking strategies for RAG data preparation.

Three deterministic strategies, each returning a list of chunk dicts with
``doc_id``, ``chunk_id`` and ``text`` keys:

- ``fixed_char_chunks`` — fixed-size character slices, no overlap.
- ``sentence_chunks`` — sentence boundaries, grouped up to ``max_chars``.
- ``sliding_window_chunks`` — fixed-size windows with a character overlap.
"""

import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _chunk(doc_id, texts):
    return [
        {"doc_id": doc_id, "chunk_id": i, "text": text}
        for i, text in enumerate(texts)
        if text.strip()
    ]


def fixed_char_chunks(text, doc_id, size=200):
    """Split text into consecutive fixed-size slices; join == original."""
    if not text.strip():
        return []
    return _chunk(doc_id, [text[i : i + size] for i in range(0, len(text), size)])


def sentence_chunks(text, doc_id, max_chars=300):
    """Split on sentence boundaries; group sentences up to ``max_chars``.

    A single sentence longer than ``max_chars`` becomes its own chunk.
    """
    if not text.strip():
        return []
    sentences = [s.strip() for s in SENTENCE_END.split(text.strip()) if s.strip()]
    grouped, current = [], ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            grouped.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        grouped.append(current)
    return _chunk(doc_id, grouped)


def sliding_window_chunks(text, doc_id, size=200, overlap=50):
    """Fixed-size windows; each window after the first repeats ``overlap``
    characters from the previous window so no idea is lost at a cut."""
    if not text.strip():
        return []
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    if len(text) <= size:
        return _chunk(doc_id, [text])
    texts, start = [], 0
    while start < len(text):
        texts.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += size - overlap
    return _chunk(doc_id, texts)


STRATEGIES = {
    "fixed": fixed_char_chunks,
    "sentence": sentence_chunks,
    "sliding": sliding_window_chunks,
}


def chunk_corpus(docs, strategy, **kwargs):
    """Chunk every document in ``docs`` with the named strategy."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    chunks = []
    for doc in docs:
        chunks.extend(STRATEGIES[strategy](doc["text"], doc["id"], **kwargs))
    return chunks
