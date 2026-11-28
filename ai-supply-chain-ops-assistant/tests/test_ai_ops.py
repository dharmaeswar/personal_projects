"""Tests for the AI Supply Chain Ops Assistant."""

import threading

import pytest

from ai_ops.analytics import (
    at_risk_orders,
    days_of_cover,
    fill_rate,
    low_cover,
    reorder_point,
    stockouts,
    answer as analytics_answer,
)
from ai_ops.evaluate import run_eval
from ai_ops.knowledge import RUNBOOKS, answer as knowledge_answer, retrieve
from ai_ops.service import Handler, STORE, ask
from ai_ops.workflows import WorkflowStore, draft_reorders, draft_transfer
from http.server import ThreadingHTTPServer
import json
import urllib.request


# --- Knowledge discovery ---

def test_retrieve_finds_reorder_runbook():
    ranked = retrieve("How is the reorder point calculated?")
    assert ranked[0][1]["id"] == "RB-REORDER-03"
    assert ranked[0][0] >= 0.20


def test_answer_cites_source():
    result = knowledge_answer("What do we do when a delivery carton count does not match?")
    assert not result["abstained"]
    assert result["sources"][0]["id"] == "RB-RECEIVING-01"
    assert "discrepancy" in result["answer"]


def test_answer_abstains_when_unanswerable():
    result = knowledge_answer("What discount do employees get on pet insurance?")
    assert result["abstained"]
    assert result["sources"] == []
    assert "don't know" in result["answer"].lower()


def test_every_runbook_has_id_and_text():
    assert len(RUNBOOKS) == 6
    for rb in RUNBOOKS:
        assert rb["id"].startswith("RB-")
        assert len(rb["text"]) > 50


# --- Analytics ---

def test_days_of_cover():
    assert days_of_cover({"on_hand": 120, "daily_demand": 40}) == 3.0
    assert days_of_cover({"on_hand": 15, "daily_demand": 35}) == 0.4


def test_reorder_point_uses_safety_stock():
    row = {"daily_demand": 40, "demand_std": 8, "lead_time_days": 3}
    # 40*3 + 1.65*8*sqrt(3) = 120 + 22.9 = 142.9
    assert reorder_point(row) == pytest.approx(142.9, abs=0.1)


def test_fill_rate_is_recomputed():
    assert fill_rate() == 0.75  # 3 of 4 open order lines fillable


def test_stockouts_lists_zero_on_hand():
    rows = stockouts()
    assert len(rows) == 1
    assert rows[0]["sku"] == "PET-TOY-014"
    assert rows[0]["warehouse"] == "FC-NORTH"


def test_low_cover_worst_first():
    rows = low_cover()
    assert rows[0]["sku"] == "PET-TREAT-030"
    assert all(r["days_of_cover"] < 7 for r in rows)


def test_at_risk_orders_follow_carrier_rule():
    at_risk = at_risk_orders("LANE-A", 96)
    ids = [o["order_id"] for o in at_risk]
    assert ids == ["ORD-1001", "ORD-1003"]
    # 96h > 72h, but only orders above $75 get a reroute suggestion.
    by_id = {o["order_id"]: o for o in at_risk}
    assert by_id["ORD-1001"]["reroute_suggested"] is True
    assert by_id["ORD-1003"]["reroute_suggested"] is False


def test_at_risk_orders_short_delay():
    at_risk = at_risk_orders("LANE-A", 24)
    assert [o["order_id"] for o in at_risk] == []


def test_analytics_answer_fill_rate():
    result = analytics_answer("What is the fill rate?")
    assert "75.0%" in result["answer"]
    assert "method" in result


def test_analytics_answer_unknown_question():
    result = analytics_answer("What is the weather in Buffalo?")
    assert result["value"] is None


# --- Workflows ---

def test_draft_reorders_only_below_reorder_point():
    store = WorkflowStore()
    tasks, created = draft_reorders(store)
    assert created == len(tasks) > 0
    assert all(t["status"] == "draft" for t in tasks)
    assert all(t["kind"] == "reorder" for t in tasks)


def test_draft_reorders_idempotent():
    store = WorkflowStore()
    _, created1 = draft_reorders(store)
    tasks2, created2 = draft_reorders(store)
    assert created2 == 0
    assert len(store.list_tasks()) == created1
    assert all(t["id"] == t2["id"] for t, t2 in zip(store.list_tasks(), tasks2))


def test_review_approve_and_reject():
    store = WorkflowStore()
    tasks, _ = draft_reorders(store)
    approved = store.review(tasks[0]["id"], approve=True, reviewer="ops-lead")
    assert approved["status"] == "approved"
    rejected = store.review(tasks[1]["id"], approve=False, reviewer="ops-lead")
    assert rejected["status"] == "rejected"
    assert len(store.audit) == len(tasks) + 2


def test_review_unknown_task_raises():
    store = WorkflowStore()
    with pytest.raises(KeyError):
        store.review("TASK-9999", approve=True, reviewer="ops-lead")


def test_review_twice_raises():
    store = WorkflowStore()
    tasks, _ = draft_reorders(store)
    store.review(tasks[0]["id"], approve=True, reviewer="ops-lead")
    with pytest.raises(ValueError):
        store.review(tasks[0]["id"], approve=True, reviewer="ops-lead")


def test_transfer_refuses_last_units():
    store = WorkflowStore()
    with pytest.raises(ValueError, match="last units"):
        draft_transfer(store, "PET-TOY-014", "FC-SOUTH", "FC-NORTH", 220)


def test_transfer_drafts_valid_move():
    store = WorkflowStore()
    task = draft_transfer(store, "PET-TOY-014", "FC-SOUTH", "FC-NORTH", 50)
    assert task["kind"] == "transfer"
    assert task["status"] == "draft"


# --- Evaluation harness ---

def test_eval_passes_all_representative_tasks():
    report = run_eval()
    assert report["total"] == 7
    assert report["failed"] == 0, [r for r in report["results"] if not r["passed"]]
    assert report["pass_rate"] == 1.0


# --- Service routing + HTTP smoke test ---

def test_ask_routes_analytics_and_knowledge():
    assert ask("What is the fill rate?")["source"] == "analytics"
    assert ask("How is the reorder point calculated?")["source"] == "knowledge"


def test_http_endpoints():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            assert json.loads(resp.read()) == {"status": "ok"}
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/ask",
            data=json.dumps({"question": "What is the fill rate?"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
            assert "75.0%" in body["answer"]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/eval",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
            assert body["failed"] == 0
    finally:
        server.shutdown()
        server.server_close()
