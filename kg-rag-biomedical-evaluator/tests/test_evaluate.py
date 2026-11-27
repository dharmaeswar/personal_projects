"""Tests for the benchmark harness and the feedback log."""

from kg_rag.corpus import DOCUMENTS, QUESTIONS
from kg_rag.evaluate import benchmark, evaluate_one
from kg_rag.feedback import FeedbackLog
from kg_rag.graph import KnowledgeGraph
from kg_rag.retrieval import TfidfRanker


def _setup():
    return KnowledgeGraph.build(DOCUMENTS), TfidfRanker(DOCUMENTS)


def test_evaluate_one_perfect_retrieval_scores_one():
    row = evaluate_one(QUESTIONS[0], DOCUMENTS, ["D01"])
    assert row["recall@3"] == 1.0
    assert row["precision@3"] == 1.0
    assert row["groundedness"] == 1.0


def test_evaluate_one_miss_scores_zero_recall():
    row = evaluate_one(QUESTIONS[0], DOCUMENTS, ["D12"])
    assert row["recall@3"] == 0.0
    assert row["abstained"] is True


def test_benchmark_kg_rag_beats_text_only_on_recall():
    graph, ranker = _setup()
    result = benchmark(DOCUMENTS, QUESTIONS, graph, ranker)
    assert result["summary"]["kg_rag"]["recall@3"] > result["summary"]["text_only"]["recall@3"]
    assert result["summary"]["kg_rag"]["recall@3"] >= 0.8


def test_benchmark_groundedness_is_one_for_both():
    graph, ranker = _setup()
    result = benchmark(DOCUMENTS, QUESTIONS, graph, ranker)
    assert result["summary"]["kg_rag"]["groundedness"] == 1.0
    assert result["summary"]["text_only"]["groundedness"] == 1.0


def test_benchmark_covers_all_questions():
    graph, ranker = _setup()
    result = benchmark(DOCUMENTS, QUESTIONS, graph, ranker)
    assert len(result["per_question"]["kg_rag"]) == len(QUESTIONS)
    assert len(result["per_question"]["text_only"]) == len(QUESTIONS)


def test_feedback_reject_downweights_edges():
    graph, _ = _setup()
    log = FeedbackLog()
    log.record("Q1", "reject", "answer cited the wrong gene",
               [("Olaparib", "TARGETS", "BRCA1")])
    log.apply_to(graph)
    edge = next(e for e in graph.edges
                if (e["subj"], e["relation"], e["obj"]) == ("Olaparib", "TARGETS", "BRCA1"))
    assert edge["weight"] == 0.5


def test_feedback_accept_upweights_edges():
    graph, _ = _setup()
    log = FeedbackLog()
    log.record("Q1", "accept", "correct drug-gene link",
               [("Olaparib", "TARGETS", "BRCA1")])
    log.apply_to(graph)
    edge = next(e for e in graph.edges
                if (e["subj"], e["relation"], e["obj"]) == ("Olaparib", "TARGETS", "BRCA1"))
    assert edge["weight"] == 1.25


def test_feedback_rejects_bad_verdict():
    log = FeedbackLog()
    try:
        log.record("Q1", "maybe", "unclear", [])
    except ValueError:
        return
    raise AssertionError("expected ValueError for verdict 'maybe'")


def test_feedback_audit_log_records_everything():
    log = FeedbackLog()
    log.record("Q1", "reject", "wrong gene", [("Olaparib", "TARGETS", "BRCA1")])
    text = log.audit_text()
    assert "Q1 reject" in text
    assert "wrong gene" in text


def test_feedback_does_not_delete_edges():
    graph, _ = _setup()
    before = len(graph.edges)
    log = FeedbackLog()
    log.record("Q1", "reject", "wrong gene",
               [("Olaparib", "TARGETS", "BRCA1")])
    log.apply_to(graph)
    assert len(graph.edges) == before
