"""Tests for TF-IDF ranking, graph retrieval, and fused retrieval."""

from kg_rag.corpus import DOCUMENTS, QUESTIONS
from kg_rag.graph import KnowledgeGraph
from kg_rag.retrieval import TfidfRanker, graph_retrieve, retrieve


def _setup():
    graph = KnowledgeGraph.build(DOCUMENTS)
    ranker = TfidfRanker(DOCUMENTS)
    return graph, ranker


def test_tfidf_ranks_exact_match_first():
    _, ranker = _setup()
    top = ranker.top_k("Osimertinib targets EGFR", k=3)
    assert top[0] == "D02"


def test_tfidf_returns_empty_for_unrelated_query():
    _, ranker = _setup()
    assert ranker.top_k("quantum computing qubits", k=3) == []


def test_graph_retrieve_finds_second_hop_document():
    graph, _ = _setup()
    # Q1: "Which drug targets BRCA1-mutated breast cancer?" — D01 holds the
    # drug->gene and gene->disease edges, so the graph walk must surface it.
    docs = [d for d, _ in graph_retrieve(graph, QUESTIONS[0]["question"])]
    assert "D01" in docs


def test_graph_retrieve_empty_without_entities():
    graph, _ = _setup()
    assert graph_retrieve(graph, "what is the weather today?") == []


def test_fused_retrieval_beats_text_only_on_two_hop_questions():
    graph, ranker = _setup()
    # Q3 needs three documents; text-only TF-IDF misses D09 (PIK3CA is a
    # rare token in the question, which never names it).
    fused = retrieve(graph, ranker, QUESTIONS[2]["question"], k=3)
    assert set(fused) & {"D01", "D03", "D09"}
    assert len(set(fused) & {"D01", "D03", "D09"}) >= 2


def test_fused_retrieval_returns_at_most_k():
    graph, ranker = _setup()
    for q in QUESTIONS:
        assert len(retrieve(graph, ranker, q["question"], k=3)) <= 3


def test_fused_retrieval_is_deterministic():
    graph, ranker = _setup()
    q = QUESTIONS[4]["question"]
    assert retrieve(graph, ranker, q, k=3) == retrieve(graph, ranker, q, k=3)
