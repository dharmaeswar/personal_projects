"""Chunking invariants: coverage, no empty chunks, overlap, sentence ends."""

from rag_evaluator.chunking import (
    chunk_corpus,
    fixed_char_chunks,
    sentence_chunks,
    sliding_window_chunks,
)
from rag_evaluator.corpus import DOCS

TEXT = (
    "First sentence about pipelines. Second sentence about data quality! "
    "Third sentence asks a question? Fourth sentence ends the passage."
)


def test_fixed_chunks_rejoin_to_original():
    chunks = fixed_char_chunks(TEXT, "d", size=20)
    assert "".join(c["text"] for c in chunks) == TEXT


def test_fixed_chunk_sizes_bounded():
    chunks = fixed_char_chunks(TEXT, "d", size=20)
    assert all(len(c["text"]) <= 20 for c in chunks)
    assert len(chunks) == (len(TEXT) + 19) // 20


def test_fixed_no_empty_chunks():
    assert all(c["text"].strip() for c in fixed_char_chunks(TEXT, "d", size=7))


def test_sentence_chunks_end_with_sentence_punctuation():
    chunks = sentence_chunks(TEXT, "d", max_chars=60)
    assert len(chunks) >= 2
    assert all(c["text"][-1] in ".!?" for c in chunks)


def test_sentence_chunks_keep_every_sentence():
    chunks = sentence_chunks(TEXT, "d", max_chars=60)
    joined = " ".join(c["text"] for c in chunks)
    for sentence in (
        "First sentence about pipelines.",
        "Second sentence about data quality!",
        "Third sentence asks a question?",
        "Fourth sentence ends the passage.",
    ):
        assert sentence in joined


def test_sliding_overlap_repeats_previous_window_tail():
    chunks = sliding_window_chunks(TEXT, "d", size=40, overlap=10)
    assert len(chunks) >= 2
    for prev, cur in zip(chunks, chunks[1:]):
        if len(prev["text"]) == 40:
            assert cur["text"].startswith(prev["text"][-10:])


def test_sliding_covers_full_text():
    chunks = sliding_window_chunks(TEXT, "d", size=40, overlap=10)
    assert chunks[0]["text"].startswith(TEXT[:40])
    assert chunks[-1]["text"].endswith(TEXT[-10:])


def test_short_text_is_one_chunk_for_every_strategy():
    short = "Only one sentence here."
    assert len(fixed_char_chunks(short, "d", size=200)) == 1
    assert len(sentence_chunks(short, "d")) == 1
    assert len(sliding_window_chunks(short, "d", size=200, overlap=50)) == 1


def test_empty_text_has_no_chunks():
    for fn in (fixed_char_chunks, sentence_chunks, sliding_window_chunks):
        assert fn("", "d") == []
        assert fn("   ", "d") == []


def test_chunk_corpus_covers_all_docs():
    for strategy in ("fixed", "sentence", "sliding"):
        chunks = chunk_corpus(DOCS, strategy)
        assert {c["doc_id"] for c in chunks} == {d["id"] for d in DOCS}
        assert all(c["text"].strip() for c in chunks)
