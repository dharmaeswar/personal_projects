"""Sentence-aware passage chunking for the knowledge layer.

Splits each document into passages of at most ~120 words, keeping the
document id, kind, title, and passage index on every chunk so retrieved
evidence can always be cited back to its source.
"""

import re

MAX_WORDS = 120


def split_sentences(text):
    """Split text into sentences on . ! ? followed by whitespace."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_document(doc, max_words=MAX_WORDS):
    """Chunk one document dict into passage dicts."""
    sentences = split_sentences(doc["text"])
    passages = []
    current = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            passages.append(" ".join(current))
            current = [sentence]
            current_words = words
        else:
            current.append(sentence)
            current_words += words
    if current:
        passages.append(" ".join(current))
    return [
        {
            "doc_id": doc["id"],
            "kind": doc["kind"],
            "title": doc["title"],
            "passage_index": i,
            "text": text,
        }
        for i, text in enumerate(passages)
    ]


def chunk_corpus(documents, max_words=MAX_WORDS):
    """Chunk every document in a corpus list."""
    chunks = []
    for doc in documents:
        chunks.extend(chunk_document(doc, max_words=max_words))
    return chunks
