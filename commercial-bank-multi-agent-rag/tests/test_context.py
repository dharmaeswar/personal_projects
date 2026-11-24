from bank_rag.context import build_context, context_text

RETRIEVED = [
    {"doc_id": "Northgate Logistics Group|financials", "borrower": "Northgate Logistics Group",
     "kind": "financials", "text": "Northgate Logistics Group reported revenue of 850.0 million dollars.",
     "score": 1.0, "source": "numeric-table"},
    {"doc_id": "Northgate Logistics Group|memo", "borrower": "Northgate Logistics Group",
     "kind": "memo", "text": "Fuel cost pressure reduced operating margins this year. Fleet expansion added revenue.",
     "score": 0.2, "source": "text-search"},
]


def test_numeric_chunks_packed_first():
    context = build_context(RETRIEVED, budget_chars=1200)
    assert context["chunks"][0]["source"] == "numeric-table"
    assert context["citations"] == ["Northgate Logistics Group|financials",
                                    "Northgate Logistics Group|memo"]


def test_budget_truncates_and_reports_it():
    context = build_context(RETRIEVED, budget_chars=60)
    assert context["truncated"] is True
    assert context["chars_used"] <= 60


def test_duplicate_sentences_dropped():
    doubled = RETRIEVED + [dict(RETRIEVED[0])]
    context = build_context(doubled, budget_chars=1200)
    texts = [c["text"] for c in context["chunks"]]
    assert len(texts) == len(set(texts))


def test_context_text_carries_citations():
    context = build_context(RETRIEVED, budget_chars=1200)
    rendered = context_text(context)
    assert "[Northgate Logistics Group|financials]" in rendered
