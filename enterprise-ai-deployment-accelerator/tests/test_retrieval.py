"""Tests for retrieval and citations."""

import pytest

from enterprise_ai_deployment import DocStore, Document


def _store():
    store = DocStore()
    store.add(Document("POL-001", "Password Reset Policy",
                       "Employees reset passwords through the self-service "
                       "portal. A reset link expires after 30 minutes."))
    store.add(Document("POL-002", "VPN Access Policy",
                       "Remote access requires VPN with multi-factor "
                       "authentication."))
    return store


def test_search_ranks_matching_doc_first():
    hits = _store().search("How do I reset my password?")
    assert hits[0].doc_id == "POL-001"


def test_search_returns_empty_for_unrelated_query():
    assert _store().search("flight refunds") == []


def test_search_respects_top_k():
    assert len(_store().search("policy access", top_k=1)) == 1


def test_duplicate_doc_id_rejected():
    store = _store()
    with pytest.raises(ValueError):
        store.add(Document("POL-001", "Copy", "text"))


def test_citations_carry_doc_id_and_title():
    store = _store()
    hits = store.search("reset my password")
    assert store.cite(hits)[0] == "[POL-001] Password Reset Policy"
