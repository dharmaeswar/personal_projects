"""Tests for the Rapid Prototype Workbench.

Covers: idea brief validation, prototype scaffolding rules, the
feedback pipeline (validation, dedupe, quarantine, metrics), the
iterate/pivot/kill decisions, the HTTP service (API + frontend page),
and the AI-agent tool surface (JSON-RPC tools/list and tools/call).
"""

import json
import threading
import urllib.request

import pytest

from prototype_lab.agent_tools import Workbench
from prototype_lab.feedback import decide
from prototype_lab.ideas import IdeaStore
from prototype_lab.pipeline import FeedbackPipeline
from prototype_lab.scaffold import PrototypeStore
from prototype_lab.service import serve

IDEA = {
    "slug": "devtool-error-explainer",
    "title": "Plain-language API error explainer",
    "problem": "Developers waste hours decoding cryptic API error codes.",
    "target_user": "Developers integrating a payments API for the first time",
    "hypothesis": "A plain-language explanation raises first-try success.",
    "success_metric": "70% complete a first charge without docs in 10 minutes",
}


def make_idea(store=None):
    store = store or IdeaStore()
    return store.create(**IDEA), store


def feedback_rows(slug, ratings, day="2026-11-26"):
    return [{"user_id": f"u{i:02d}", "prototype_slug": slug, "rating": r,
             "comment": "", "day": day} for i, r in enumerate(ratings)]


# --- ideas ---

def test_create_idea_stores_all_fields():
    idea, _ = make_idea()
    assert idea.slug == "devtool-error-explainer"
    assert idea.status == "open"
    assert idea.success_metric.startswith("70%")


def test_create_idea_rejects_empty_field():
    store = IdeaStore()
    bad = dict(IDEA, problem="   ")
    with pytest.raises(ValueError, match="problem"):
        store.create(**bad)


def test_create_idea_rejects_bad_slug():
    store = IdeaStore()
    with pytest.raises(ValueError, match="slug"):
        store.create(**dict(IDEA, slug="Bad Slug!"))


def test_create_idea_rejects_duplicate_slug():
    idea, store = make_idea()
    with pytest.raises(ValueError, match="already exists"):
        store.create(**IDEA)


def test_set_status_rejects_unknown_status():
    idea, store = make_idea()
    with pytest.raises(ValueError, match="status"):
        store.set_status(idea.slug, "shipped")


def test_list_filters_by_status():
    _, store = make_idea()
    store.create(**dict(IDEA, slug="one-tap-tip-jar", title="One-tap tip jar"))
    store.set_status("one-tap-tip-jar", "killed")
    assert [i.slug for i in store.list(status="killed")] == ["one-tap-tip-jar"]
    assert len(store.list()) == 2


# --- scaffolding ---

def test_scaffold_builds_full_stack_shape():
    idea, _ = make_idea()
    proto = PrototypeStore().scaffold(idea, build_minutes=180)
    assert proto.slug == "devtool-error-explainer-v1"
    assert proto.status == "scaffolding"
    assert {"method": "POST", "path": "/api/feedback"} in proto.api_routes
    assert proto.pipeline_stages == ["ingest", "validate", "dedupe", "aggregate"]
    assert proto.frontend_page == "/prototypes/devtool-error-explainer"
    assert proto.build_minutes == 180


def test_scaffold_rejects_week_long_build():
    idea, _ = make_idea()
    with pytest.raises(ValueError, match="rapid prototyping"):
        PrototypeStore().scaffold(idea, build_minutes=60 * 24 * 6)


def test_scaffold_rejects_second_live_prototype():
    idea, _ = make_idea()
    store = PrototypeStore()
    store.scaffold(idea, build_minutes=60)
    with pytest.raises(ValueError, match="already has a live prototype"):
        store.scaffold(idea, build_minutes=60)


def test_launch_requires_scaffolding_state():
    idea, _ = make_idea()
    store = PrototypeStore()
    proto = store.scaffold(idea, build_minutes=60)
    assert store.launch(idea.slug).status == "running"
    with pytest.raises(ValueError, match="only a scaffolding prototype can launch"):
        store.launch(idea.slug)


def test_retired_prototype_frees_the_idea():
    idea, _ = make_idea()
    store = PrototypeStore()
    store.scaffold(idea, build_minutes=60)
    store.set_status(idea.slug, "retired")
    proto2 = store.scaffold(idea, build_minutes=90)
    assert proto2.build_minutes == 90


# --- feedback pipeline ---

def test_ingest_accepts_and_counts():
    pipe = FeedbackPipeline()
    assert pipe.ingest({"user_id": "u1", "prototype_slug": "p-v1", "rating": 5,
                        "comment": "great", "day": "2026-11-26"}) == "accepted"
    assert len(pipe.events) == 1


def test_ingest_rejects_bad_rating_and_quarantines_with_reason():
    pipe = FeedbackPipeline()
    assert pipe.ingest({"user_id": "u1", "prototype_slug": "p-v1", "rating": 6,
                        "day": "2026-11-26"}) == "quarantined"
    assert pipe.quarantined[0].reason == "rating must be an integer 1-5"
    assert pipe.events == []


def test_ingest_rejects_bad_day_format():
    pipe = FeedbackPipeline()
    assert pipe.ingest({"user_id": "u1", "prototype_slug": "p-v1", "rating": 4,
                        "day": "11/26/2026"}) == "quarantined"
    assert "YYYY-MM-DD" in pipe.quarantined[0].reason


def test_ingest_dedupes_same_user_same_day():
    pipe = FeedbackPipeline()
    row = {"user_id": "u1", "prototype_slug": "p-v1", "rating": 5, "day": "2026-11-26"}
    assert pipe.ingest(row) == "accepted"
    assert pipe.ingest(row) == "duplicate"
    assert pipe.ingest(dict(row, day="2026-11-27")) == "accepted"
    assert len(pipe.events) == 2


def test_metrics_aggregate_correctly():
    pipe = FeedbackPipeline()
    pipe.ingest_many(feedback_rows("p-v1", [5, 4, 5, 2, 3, 5, 4, 5, 5, 4, 5, 4]))
    m = pipe.metrics("p-v1")
    assert m["count"] == 12
    assert m["avg_rating"] == 4.25
    assert m["promoter_share"] == 0.83
    assert m["detractor_share"] == 0.08
    assert m["per_day"] == {"2026-11-26": 12}


def test_metrics_none_without_feedback():
    assert FeedbackPipeline().metrics("p-v1") is None


def test_comments_returns_only_non_empty():
    pipe = FeedbackPipeline()
    pipe.ingest_many([
        {"user_id": "u1", "prototype_slug": "p-v1", "rating": 5, "comment": "loved it", "day": "2026-11-26"},
        {"user_id": "u2", "prototype_slug": "p-v1", "rating": 4, "comment": "", "day": "2026-11-26"},
    ])
    assert pipe.comments("p-v1") == ["loved it"]


# --- decisions ---

def test_decide_iterate_on_strong_feedback():
    decision, _ = decide({"count": 12, "avg_rating": 4.5, "promoter_share": 0.75,
                          "detractor_share": 0.0, "per_day": {}})
    assert decision == "iterate"


def test_decide_kill_on_weak_feedback():
    decision, _ = decide({"count": 11, "avg_rating": 2.0, "promoter_share": 0.09,
                          "detractor_share": 0.73, "per_day": {}})
    assert decision == "kill"


def test_decide_pivot_on_middling_feedback():
    decision, _ = decide({"count": 12, "avg_rating": 3.17, "promoter_share": 0.33,
                          "detractor_share": 0.17, "per_day": {}})
    assert decision == "pivot"


def test_decide_not_enough_data_below_threshold():
    decision, reason = decide({"count": 4, "avg_rating": 5.0, "promoter_share": 1.0,
                               "detractor_share": 0.0, "per_day": {}})
    assert decision == "not_enough_data"
    assert "need 10" in reason


def test_decide_none_metrics_is_not_enough_data():
    assert decide(None)[0] == "not_enough_data"


# --- HTTP service ---

@pytest.fixture
def running_server():
    wb = Workbench()
    wb.ideas.create(**IDEA)
    wb.prototypes.scaffold(wb.ideas.get(IDEA["slug"]), build_minutes=120)
    wb.prototypes.launch(IDEA["slug"])
    wb.pipeline.ingest_many(feedback_rows("devtool-error-explainer-v1", [5, 4, 5]))
    server = serve(wb.ideas, wb.prototypes, wb.pipeline, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()


def get(base, path):
    with urllib.request.urlopen(base + path) as resp:
        return resp.status, resp.read().decode("utf-8")


def post(base, path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_service_health_and_prototype_list(running_server):
    status, body = get(running_server, "/api/health")
    assert status == 200 and json.loads(body)["status"] == "ok"
    status, body = get(running_server, "/api/prototypes")
    protos = json.loads(body)
    assert len(protos) == 1 and protos[0]["status"] == "running"


def test_service_frontend_page_renders_idea(running_server):
    status, body = get(running_server, "/prototypes/devtool-error-explainer")
    assert status == 200
    assert "Plain-language API error explainer" in body
    assert "Developers integrating a payments API" in body


def test_service_feedback_round_trip(running_server):
    status, body = post(running_server, "/api/feedback",
                        {"user_id": "u9", "prototype_slug": "devtool-error-explainer-v1",
                         "rating": 5, "comment": "shipped it", "day": "2026-11-27"})
    assert status == 201 and body["result"] == "accepted"
    status, body = get(running_server, "/api/prototypes/devtool-error-explainer-v1/metrics")
    assert json.loads(body)["count"] == 4


def test_service_rejects_invalid_feedback(running_server):
    with pytest.raises(Exception):
        post(running_server, "/api/feedback",
             {"user_id": "u9", "prototype_slug": "devtool-error-explainer-v1",
              "rating": 9, "day": "2026-11-27"})


# --- agent tools (JSON-RPC) ---

def test_agent_tools_list():
    wb = Workbench()
    resp = wb.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["list_ideas", "scaffold_prototype", "submit_feedback", "prototype_metrics"]


def test_agent_full_loop_end_to_end():
    wb = Workbench()
    wb.ideas.create(**IDEA)
    resp = wb.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "scaffold_prototype",
                                 "arguments": {"idea_slug": IDEA["slug"], "build_minutes": 90}}})
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["slug"] == "devtool-error-explainer-v1"
    assert result["frontend_page"] == "/prototypes/devtool-error-explainer"
    for i, rating in enumerate([5, 5, 4, 5, 4, 5, 4, 5, 5, 4, 5, 4]):
        wb.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": "submit_feedback",
                              "arguments": {"user_id": f"u{i:02d}",
                                            "prototype_slug": "devtool-error-explainer-v1",
                                            "rating": rating, "day": "2026-11-26"}}})
    resp = wb.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "prototype_metrics",
                                 "arguments": {"prototype_slug": "devtool-error-explainer-v1"}}})
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["count"] == 12 and result["decision"] == "iterate"


def test_agent_unknown_tool_errors():
    wb = Workbench()
    resp = wb.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "delete_everything", "arguments": {}}})
    assert resp["error"]["code"] == -32601


def test_agent_bad_arguments_error_not_crash():
    wb = Workbench()
    resp = wb.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "scaffold_prototype",
                                 "arguments": {"idea_slug": "no-such-idea"}}})
    assert resp["error"]["code"] == -32602
