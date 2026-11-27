"""Tests for grounded answer composition."""

from kg_rag.corpus import DOCUMENTS, QUESTIONS
from kg_rag.qa import answer, groundedness


def test_answer_cites_every_claim():
    result = answer(QUESTIONS[0]["question"], DOCUMENTS, ["D01"])
    assert not result["abstained"]
    assert result["claims"]
    for claim in result["claims"]:
        assert claim["source"] == "D01"
        assert f"[{claim['source']}]" in result["answer"]


def test_answer_only_uses_retrieved_documents():
    result = answer(QUESTIONS[0]["question"], DOCUMENTS, ["D01"])
    sources = {c["source"] for c in result["claims"]}
    assert sources <= {"D01"}


def test_answer_abstains_when_nothing_retrieved():
    result = answer(QUESTIONS[0]["question"], DOCUMENTS, [])
    assert result["abstained"]
    assert "Not covered by the documents" in result["answer"]
    assert result["claims"] == []


def test_answer_abstains_when_retrieved_docs_are_irrelevant():
    # D12 is about Alzheimer's; Q1 is about BRCA1 breast cancer.
    result = answer(QUESTIONS[0]["question"], DOCUMENTS, ["D12"])
    assert result["abstained"]


def test_answer_mentions_expected_entities():
    result = answer(QUESTIONS[1]["question"], DOCUMENTS, ["D02"])
    text = " ".join(c["text"] for c in result["claims"])
    assert "Osimertinib" in text
    assert "EGFR" in text


def test_groundedness_is_one_when_all_claims_cited():
    result = answer(QUESTIONS[3]["question"], DOCUMENTS, ["D04"])
    assert groundedness(result, {"D04"}) == 1.0


def test_groundedness_counts_uncited_claims():
    result = {"claims": [{"text": "X", "source": "D01"},
                         {"text": "Y", "source": "D99"}],
              "abstained": False}
    assert groundedness(result, {"D01"}) == 0.5


def test_groundedness_of_abstention_is_one():
    result = {"claims": [], "abstained": True}
    assert groundedness(result, set()) == 1.0


def test_answer_caps_claims_at_four():
    result = answer(QUESTIONS[2]["question"], DOCUMENTS, ["D01", "D03", "D09"])
    assert len(result["claims"]) <= 4
