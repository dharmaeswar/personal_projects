from bank_rag.corpus import build_corpus
from bank_rag.retrieval import TextIndex, find_borrower, hybrid_retrieve, numeric_lookup

DOCS = build_corpus()


def test_find_borrower():
    assert find_borrower("What is Northgate Logistics Group's leverage?") == "Northgate Logistics Group"
    assert find_borrower("Tell me about the weather.") is None


def test_numeric_lookup_returns_exact_figure():
    facts = numeric_lookup("What is Northgate Logistics Group's revenue?")
    assert len(facts) == 1
    assert facts[0]["metric"] == "revenue"
    assert facts[0]["value"] == 850.0


def test_numeric_lookup_empty_without_borrower():
    assert numeric_lookup("What is the leverage ratio?") == []


def test_text_index_ranks_memo_first_for_supply_chain():
    index = TextIndex(DOCS)
    scored = index.score("supply-chain risk single-source supplier")
    assert scored[0][1]["doc_id"] == "Summit Ridge Manufacturing|memo"


def test_hybrid_retrieve_puts_numeric_facts_first():
    results = hybrid_retrieve("What is BlueRock Packaging Co's total debt?", DOCS, TextIndex(DOCS))
    assert results[0]["source"] == "numeric-table"
    assert "384.0" in results[0]["text"]


def test_hybrid_retrieve_caps_text_hits_not_numeric_facts():
    results = hybrid_retrieve("Is BlueRock Packaging Co in compliance with its leverage covenant?",
                              DOCS, TextIndex(DOCS), k=2)
    text_hits = [r for r in results if r["source"] == "text-search"]
    numeric = [r for r in results if r["source"] == "numeric-table"]
    assert len(text_hits) <= 2
    assert len(numeric) == 5  # covenant check needs every figure
