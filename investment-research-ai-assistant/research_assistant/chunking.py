"""Sentence-aware chunking of research documents into passages."""

import re

from dataclasses import dataclass

from .corpus import Document

MAX_WORDS = 120


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    company: str
    doc_type: str
    date: str
    section: str
    text: str


def _split_sentences(text):
    """Split on sentence-ending punctuation followed by whitespace.

    Decimal points (e.g. "$4.2 billion") are not sentence ends.
    """
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def chunk_document(doc: Document, max_words: int = MAX_WORDS):
    """Split one document into passages of at most max_words, sentence-aware."""
    sentences = _split_sentences(doc.text)
    chunks = []
    current = []
    current_words = 0
    index = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            chunk_text = " ".join(current)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#c{index}",
                    doc_id=doc.doc_id,
                    company=doc.company,
                    doc_type=doc.doc_type,
                    date=doc.date,
                    section=doc.section,
                    text=chunk_text,
                )
            )
            index += 1
            current = []
            current_words = 0
        current.append(sentence)
        current_words += words
    if current:
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#c{index}",
                doc_id=doc.doc_id,
                company=doc.company,
                doc_type=doc.doc_type,
                date=doc.date,
                section=doc.section,
                text=" ".join(current),
            )
        )
    return chunks


def chunk_corpus(documents, max_words: int = MAX_WORDS):
    """Chunk every document; returns a flat list of chunks in corpus order."""
    chunks = []
    for doc in documents:
        chunks.extend(chunk_document(doc, max_words=max_words))
    return chunks
