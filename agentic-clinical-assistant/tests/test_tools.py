import pytest

from clinical_agent.tools import ToolError, ToolServer


def test_search_kb_returns_ranked_hits():
    server = ToolServer()
    hits = server.call("search_kb", query="diabetes follow-up")
    assert hits
    assert hits[0]["doc_id"] == "KB-001"
    assert {"doc_id", "title", "snippet", "score"} <= set(hits[0])


def test_search_kb_requires_query():
    server = ToolServer()
    with pytest.raises(ToolError, match="missing required argument"):
        server.call("search_kb", query="")


def test_patient_context_is_deidentified():
    server = ToolServer()
    context = server.call("get_patient_context", patient_id="P-1001")
    assert context["conditions"] == ["type 2 diabetes", "hypertension"]
    assert "Alice Johnson" not in str(context)
    assert "MRN-482913" not in str(context)
    assert "03/14/1962" not in str(context)


def test_unknown_patient_raises():
    server = ToolServer()
    with pytest.raises(ToolError, match="unknown patient_id"):
        server.call("get_patient_context", patient_id="P-9999")


def test_escalation_without_approval_is_denied():
    server = ToolServer()
    with pytest.raises(ToolError, match="requires human approval"):
        server.call(
            "escalate_to_clinician",
            patient_id="P-1001",
            reason="chest pain",
            approved=False,
        )


def test_escalation_with_approval_succeeds():
    server = ToolServer()
    result = server.call(
        "escalate_to_clinician",
        patient_id="P-1001",
        reason="chest pain",
        approved=True,
    )
    assert result["escalated"] is True
    assert result["status"] == "sent to on-call clinician"


def test_send_without_approval_is_denied():
    server = ToolServer()
    with pytest.raises(ToolError, match="requires human approval"):
        server.call(
            "send_message",
            patient_id="P-1002",
            message="Reminder.",
            approved=False,
        )


def test_unknown_tool_raises():
    server = ToolServer()
    with pytest.raises(ToolError, match="unknown tool"):
        server.call("delete_everything")


def test_trace_records_every_call():
    server = ToolServer()
    server.call("search_kb", query="diabetes")
    assert len(server.trace) == 1
    assert server.trace[0]["tool"] == "search_kb"
    assert server.trace[0]["outcome"] == "ok"
    assert server.trace[0]["latency_ms"] >= 0
