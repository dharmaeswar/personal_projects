from genai_platform.rag import KnowledgeBase, demo_knowledge_base


def test_retrieval_finds_covenant_chunk():
    kb = demo_knowledge_base()
    results = kb.retrieve("What is the leverage covenant limit?")
    assert results
    assert "3.5x" in results[0][0].text


def test_retrieval_returns_nothing_for_unrelated_question():
    kb = demo_knowledge_base()
    assert kb.retrieve("How do I bake sourdough bread?") == []


def test_pack_context_respects_budget_and_cites():
    kb = demo_knowledge_base()
    context, citations = kb.pack_context(
        "What needs dual authorization?", char_budget=500
    )
    assert len(context) <= 500 + 450  # one chunk may exceed the budget alone
    assert citations
    assert all("::" in citation for citation in citations)


def test_add_document_chunks_long_text():
    kb = KnowledgeBase()
    kb.add_document("D1", "Long Doc", "First sentence here. " * 60)
    assert len(kb.chunks) > 1
    assert all(chunk.doc_id == "D1" for chunk in kb.chunks)


def test_demo_kb_has_four_documents():
    kb = demo_knowledge_base()
    doc_ids = {chunk.doc_id for chunk in kb.chunks}
    assert doc_ids == {"POL-101", "RUN-204", "MRG-310", "SEC-118"}
