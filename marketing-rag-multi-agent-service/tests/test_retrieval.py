from marketing_rag.corpus import build_documents
from marketing_rag.retrieval import Retriever, tokenize


def test_tokenize_drops_stopwords():
    tokens = tokenize("The Best Campaign for Email Marketing")
    assert "the" not in tokens
    assert "best" in tokens and "email" in tokens


def test_retrieve_display_cpa_top():
    retriever = Retriever(build_documents())
    results = retriever.retrieve("Display Retargeting CPA cost per acquisition")
    assert results
    assert results[0]["id"] == "CMP-005"


def test_retrieve_scores_descending():
    retriever = Retriever(build_documents())
    results = retriever.retrieve("email launch campaign")
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(s > 0 for s in scores)


def test_retrieve_empty_query():
    retriever = Retriever(build_documents())
    assert retriever.retrieve("") == []
    assert retriever.retrieve("   ") == []


def test_retrieve_unknown_words():
    retriever = Retriever(build_documents())
    assert retriever.retrieve("zzzzqqqq") == []


def test_chunk_document_keeps_id():
    retriever = Retriever(build_documents())
    doc = build_documents()[0]
    chunks = retriever.chunk_document(doc, max_words=10)
    assert len(chunks) > 1
    assert all(c["id"] == doc["id"] for c in chunks)
    assert " ".join(c["text"] for c in chunks) == doc["text"]


def test_score_for_matches_retrieve():
    retriever = Retriever(build_documents())
    results = retriever.retrieve("Display Retargeting CPA cost per acquisition")
    assert retriever.score_for("CMP-005", "Display Retargeting CPA cost per acquisition") == results[0]["score"]
    assert retriever.score_for("NOPE-000", "Display Retargeting") == 0.0
