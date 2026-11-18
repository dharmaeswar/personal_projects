"""Retrieval maths: cosine bounds, ranking, precision/recall."""

from rag_evaluator.chunking import chunk_corpus
from rag_evaluator.corpus import DOCS, QUERIES
from rag_evaluator.retrieval import (
    build_index,
    cosine,
    embed,
    precision_at_k,
    recall_at_k,
    search,
)


def _index():
    chunks = chunk_corpus(DOCS, "sentence")
    vocab, idf = build_index(chunks)
    return chunks, vocab, idf


def test_cosine_identical_vectors_is_one():
    chunks, vocab, idf = _index()
    vec = embed("kafka streams events in real time", vocab, idf)
    assert cosine(vec, vec) == 1.0


def test_cosine_unrelated_vectors_is_zero():
    assert cosine({0: 1.0}, {1: 1.0}) == 0.0


def test_cosine_empty_vector_is_zero():
    assert cosine({}, {0: 1.0}) == 0.0
    assert cosine({0: 1.0}, {}) == 0.0


def test_scores_stay_in_zero_to_one():
    chunks, vocab, idf = _index()
    for query in QUERIES:
        for _, score in search(query["text"], chunks, vocab, idf, k=3):
            assert 0.0 <= score <= 1.0


def test_search_finds_relevant_doc_in_top_three():
    chunks, vocab, idf = _index()
    for query in QUERIES:
        hits = search(query["text"], chunks, vocab, idf, k=3)
        doc_ids = {chunk["doc_id"] for chunk, _ in hits}
        assert doc_ids & set(query["relevant"]), query["id"]


def test_empty_query_returns_zero_scores():
    chunks, vocab, idf = _index()
    hits = search("", chunks, vocab, idf, k=3)
    assert len(hits) == 3
    assert all(score == 0.0 for _, score in hits)


def test_unknown_words_return_zero_scores():
    chunks, vocab, idf = _index()
    hits = search("zzzqqq wwwppp", chunks, vocab, idf, k=3)
    assert all(score == 0.0 for _, score in hits)


def test_precision_and_recall_maths():
    assert precision_at_k(["a", "b", "c"], ["a", "x"], 3) == 1 / 3
    assert recall_at_k(["a", "b", "c"], ["a", "x"]) == 1 / 2
    assert precision_at_k([], ["a"], 3) == 0.0
    assert recall_at_k(["a"], []) == 0.0
    assert precision_at_k(["a"], ["a"], 3) == 1.0
    assert recall_at_k(["a"], ["a"]) == 1.0
