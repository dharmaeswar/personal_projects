import pytest

from agent_eval.tools import ToolError, ToolServer
from agent_eval.tracer import Tracer


@pytest.fixture
def server():
    return ToolServer(Tracer())


def test_list_tools_exposes_all_ten(server):
    names = {t["name"] for t in server.list_tools()}
    assert names == {"lookup_invoice", "lookup_po", "approve_invoice",
                     "flag_invoice", "lookup_customer", "get_ticket",
                     "search_kb", "resolve_ticket", "escalate_ticket"}


def test_lookup_invoice_returns_record(server):
    inv = server.call("lookup_invoice", {"invoice_id": "INV-1001"})
    assert inv["vendor"] == "Acme Supplies"
    assert inv["amount"] == 1250.00
    assert inv["po_id"] == "PO-5001"


def test_lookup_missing_invoice_raises_and_traces_error(server):
    with pytest.raises(ToolError, match="not found"):
        server.call("lookup_invoice", {"invoice_id": "INV-9999"})
    assert server.tracer.errors()[0].tool == "lookup_invoice"


def test_unknown_tool_raises(server):
    with pytest.raises(ToolError, match="unknown tool"):
        server.call("delete_everything", {})


def test_missing_required_argument_rejected(server):
    with pytest.raises(ToolError, match="missing required argument"):
        server.call("lookup_invoice", {})


def test_wrong_argument_type_rejected(server):
    with pytest.raises(ToolError, match="must be a string"):
        server.call("lookup_invoice", {"invoice_id": 1001})


def test_unknown_argument_rejected(server):
    with pytest.raises(ToolError, match="unknown argument"):
        server.call("lookup_invoice", {"invoice_id": "INV-1001", "extra": 1})


def test_approve_invoice_changes_status(server):
    rec = server.call("approve_invoice", {"invoice_id": "INV-1001",
                                          "approver": "tester"})
    assert rec["amount"] == 1250.00
    assert server.call("lookup_invoice", {"invoice_id": "INV-1001"})["status"] == "approved"


def test_approve_twice_is_rejected(server):
    server.call("approve_invoice", {"invoice_id": "INV-1001", "approver": "tester"})
    with pytest.raises(ToolError, match="cannot approve"):
        server.call("approve_invoice", {"invoice_id": "INV-1001", "approver": "tester"})


def test_flag_invoice_records_reason(server):
    rec = server.call("flag_invoice", {"invoice_id": "INV-1002", "reason": "amount mismatch"})
    assert rec["reason"] == "amount mismatch"
    assert server.call("lookup_invoice", {"invoice_id": "INV-1002"})["status"] == "flagged"


def test_search_kb_matches_keywords(server):
    hits = server.call("search_kb", {"query": "How do I reset my password?"})
    assert [h["article_id"] for h in hits] == ["KB-01"]


def test_search_kb_no_match_returns_empty(server):
    assert server.call("search_kb", {"query": "quantum entanglement"}) == []


def test_lookup_po_and_customer(server):
    assert server.call("lookup_po", {"po_id": "PO-5001"})["amount"] == 1250.00
    assert server.call("lookup_customer", {"customer_id": "CUST-02"})["plan"] == "enterprise"
