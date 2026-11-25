"""Tests for chunking, retrieval, grounded Q&A, guardrails, and evaluation."""

from research_assistant.chunking import chunk_corpus, chunk_document
from research_assistant.corpus import load_corpus
from research_assistant.evaluate import EVAL_CASES, evaluate
from research_assistant.guardrails import check_answer
from research_assistant.qa import ResearchAssistant
from research_assistant.retrieval import Retriever, tokenize


def test_corpus_has_twelve_documents():
    docs = load_corpus()
    assert len(docs) == 12
    assert {d.company for d in docs} == {
        "Acme Industrial Holdings",
        "Beacon Health Systems",
        "Northwind Energy Partners",
        "Helix Software Group",
    }


def test_chunking_keeps_metadata_and_word_limit():
    docs = load_corpus()
    chunks = chunk_corpus(docs)
    assert len(chunks) >= 12
    for chunk in chunks:
        assert len(chunk.text.split()) <= 120
        assert chunk.doc_id
        assert chunk.company
        assert chunk.chunk_id.startswith(chunk.doc_id + "#c")


def test_chunking_single_short_document_is_one_chunk():
    docs = load_corpus()
    chunks = chunk_document(docs[0])
    assert len(chunks) == 1
    assert chunks[0].text == docs[0].text


def test_tokenize_drops_stopwords():
    tokens = tokenize("What was the revenue for the quarter?")
    assert "revenue" in tokens
    assert "the" not in tokens
    assert "what" not in tokens


def test_retrieval_returns_acme_revenue_doc_first():
    chunks = chunk_corpus(load_corpus())
    retriever = Retriever(chunks)
    results = retriever.retrieve("Acme Industrial Holdings third-quarter revenue operating margin", top_k=3)
    assert results
    assert results[0].chunk.doc_id == "ACME-10K-2026-Q3"


def test_retrieval_returns_northwind_hedge_doc_first():
    chunks = chunk_corpus(load_corpus())
    retriever = Retriever(chunks)
    results = retriever.retrieve("Northwind oil production hedged collars floor ceiling", top_k=3)
    assert results
    assert results[0].chunk.doc_id == "NORTHWIND-RISK-2026"


def test_retrieval_empty_for_unrelated_query():
    chunks = chunk_corpus(load_corpus())
    retriever = Retriever(chunks)
    results = retriever.retrieve("quantum computing superconductors", top_k=3)
    assert results == []


def test_qa_answer_cites_sources_and_is_grounded():
    assistant = ResearchAssistant()
    answer = assistant.ask("What was Acme Industrial Holdings third-quarter revenue and operating margin?")
    assert "$4.2 billion" in answer.text
    assert "18.4 percent" in answer.text
    assert answer.citations
    assert any("ACME-10K-2026-Q3" in c for c in answer.citations)
    assert answer.grounded
    assert answer.guardrail_passed


def test_qa_answer_quotes_numbers_from_retrieved_passage_only():
    assistant = ResearchAssistant()
    answer = assistant.ask("What dividend did Northwind Energy Partners declare?")
    assert "$0.42" in answer.text
    assert answer.guardrail_passed


def test_qa_uncovered_question_says_not_covered():
    assistant = ResearchAssistant()
    answer = assistant.ask("What is the CEO's favorite restaurant in Baltimore?")
    assert answer.text.startswith("Not covered by the research notes")
    assert answer.grounded


def test_guardrail_blocks_guarantee_language():
    verdict = check_answer(
        "This stock will definitely double next year.",
        ["ACME-10K-2026-Q3"],
        ["Acme reported revenue of $4.2 billion."],
    )
    assert not verdict.passed
    assert any("guarantee" in v for v in verdict.violations)


def test_guardrail_blocks_buy_recommendation():
    verdict = check_answer(
        "You should buy shares now.",
        ["HELIX-AN-2026-10"],
        ["Helix grew subscription revenue 21 percent."],
    )
    assert not verdict.passed
    assert any("recommendation" in v for v in verdict.violations)


def test_guardrail_requires_citations():
    verdict = check_answer("Revenue grew.", [], ["Revenue grew."])
    assert not verdict.passed
    assert any("citation" in v for v in verdict.violations)


def test_guardrail_flags_mnpi_marker_in_source():
    verdict = check_answer(
        "Revenue grew.",
        ["DOC-1"],
        ["This is confidential information, do not share it."],
    )
    assert not verdict.passed
    assert any("MNPI" in v for v in verdict.violations)


def test_guardrail_passes_clean_grounded_answer():
    verdict = check_answer(
        "Acme reported revenue of $4.2 billion.",
        ["ACME-10K-2026-Q3 (filing_excerpt, 2026-10-28)"],
        ["Acme reported revenue of $4.2 billion."],
    )
    assert verdict.passed


def test_evaluation_recall_and_groundedness():
    report = evaluate()
    assert report["total_cases"] == len(EVAL_CASES) == 10
    assert report["recall_at_k"] >= 0.8
    assert report["grounded_rate"] == 1.0
    assert report["guardrail_pass_rate"] == 1.0
    assert report["hallucination_flag_rate"] == 0.0
