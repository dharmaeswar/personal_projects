"""Tests for the retrieval agent."""

from enterprise_ai_deployment import (
    Agent, DocStore, Document, build_enterprise_tools,
)


def _agent():
    store = DocStore()
    store.add(Document("POL-001", "Password Reset Policy",
                       "Employees reset passwords through the self-service "
                       "portal. A reset link expires after 30 minutes."))
    store.add(Document("POL-002", "VPN Access Policy",
                       "Remote access requires VPN with multi-factor "
                       "authentication."))
    return Agent(store, build_enterprise_tools(store))


def test_grounded_answer_cites_documents():
    answer = _agent().run("How do I reset my password?")
    assert answer.grounded is True
    assert "self-service portal" in answer.text
    assert answer.citations[0].startswith("[POL-001]")
    assert "search_kb" in answer.tools_used


def test_ungrounded_question_escalates_instead_of_inventing():
    answer = _agent().run("What is the refund policy for cancelled flights?")
    assert answer.escalated is True
    assert answer.grounded is False
    assert "escalate_to_human" in answer.tools_used
    assert "could not find" in answer.text
