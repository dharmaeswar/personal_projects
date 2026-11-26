"""Tests for the agent engine runtime: runtime, memory, retrieval,
governance, SDK, and CLI. All data is synthetic; no network or model calls.
"""

import threading
import time

import pytest

from agent_engine import (
    AgentRuntime,
    AgentStep,
    AgentTask,
    Engine,
    EpisodicMemory,
    KnowledgeIndex,
    Policy,
    SessionMemory,
    TenantContext,
    ToolRegistry,
    ToolSpec,
    WorkingMemory,
    demo_agent_steps,
)
from agent_engine.cli import build_engine, main as cli_main
from agent_engine.retrieval import Document


# --- runtime ---------------------------------------------------------------

def _ok(ctx):
    return 42


def _flaky_factory(failures):
    state = {"n": 0}

    def fn(ctx):
        state["n"] += 1
        if state["n"] <= failures:
            raise RuntimeError("transient failure")
        return "recovered"

    return fn


def test_runtime_runs_steps_in_order_and_shares_context():
    runtime = AgentRuntime()
    task = AgentTask(name="t", steps=[
        AgentStep(name="first", fn=lambda c: c.update(x=1) or 1),
        AgentStep(name="second", fn=lambda c: c["x"] + 1),
    ])
    result = runtime.run(task)
    assert result.ok
    assert result.values() == {"first": 1, "second": 2}
    assert [s.attempts for s in result.steps] == [1, 1]


def test_runtime_retries_then_recovers():
    runtime = AgentRuntime()
    task = AgentTask(name="t", steps=[
        AgentStep(name="flaky", fn=_flaky_factory(2), max_retries=2),
    ])
    result = runtime.run(task)
    assert result.ok
    assert result.steps[0].attempts == 3
    assert result.steps[0].value == "recovered"


def test_runtime_gives_up_after_retries_and_stops():
    runtime = AgentRuntime()
    ran = []

    def never(ctx):
        ran.append(1)
        raise ValueError("always fails")

    task = AgentTask(name="t", steps=[
        AgentStep(name="bad", fn=never, max_retries=1),
        AgentStep(name="after", fn=_ok),
    ])
    result = runtime.run(task)
    assert result.status == "failed"
    assert result.steps[0].attempts == 2
    assert len(result.steps) == 1  # stops at the first failed step
    assert ran == [1, 1]


def test_runtime_step_budget_exceeded():
    runtime = AgentRuntime()
    task = AgentTask(name="t", max_steps=2, steps=[
        AgentStep(name=f"s{i}", fn=_ok) for i in range(4)
    ])
    result = runtime.run(task)
    assert result.status == "budget_exceeded"
    assert all(s.status == "skipped" for s in result.steps)
    assert len(result.steps) == 2


def test_runtime_runs_agents_concurrently():
    runtime = AgentRuntime(max_workers=4)
    started = threading.Barrier(4)

    def slow(ctx):
        started.wait(timeout=5)
        time.sleep(0.05)
        return ctx.get("name")

    tasks = [AgentTask(name=f"a{i}", steps=[AgentStep(name="s", fn=slow)],
                       context={"name": f"a{i}"}) for i in range(4)]
    t0 = time.monotonic()
    results = runtime.run_many(tasks)
    elapsed = time.monotonic() - t0
    assert all(r.ok for r in results)
    assert [r.agent_name for r in results] == ["a0", "a1", "a2", "a3"]
    assert elapsed < 0.8  # sequential would take ~4x the barrier + sleep


# --- memory ----------------------------------------------------------------

def test_working_memory_caps_at_capacity():
    mem = WorkingMemory(capacity=3)
    for i in range(5):
        mem.add(f"turn {i}")
    assert len(mem) == 3
    assert mem.recent() == ["turn 2", "turn 3", "turn 4"]


def test_episodic_recall_ranks_relevant_episode_first():
    mem = EpisodicMemory()
    mem.store("The customer prefers email notifications.", tenant_id="t1")
    mem.store("Refund policy allows returns within 30 days.", tenant_id="t1")
    mem.store("Shipping takes 3 to 5 business days.", tenant_id="t1")
    hits = mem.recall("what is the refund policy", tenant_id="t1")
    assert hits[0].episode.text.startswith("Refund policy")
    assert hits[0].score > 0


def test_episodic_recall_never_crosses_tenants():
    mem = EpisodicMemory()
    mem.store("Tenant two secret refund code ALPHA.", tenant_id="t2")
    mem.store("Tenant one public refund policy.", tenant_id="t1")
    hits = mem.recall("refund code", tenant_id="t1")
    assert all(h.episode.tenant_id == "t1" for h in hits)
    assert not any("ALPHA" in h.episode.text for h in hits)


def test_session_memory_context_block_has_both_layers():
    session = SessionMemory(tenant_id="t1")
    session.remember("Customer asked about refunds.")
    block = session.context_block("refunds")
    assert "[working memory]" in block
    assert "[recalled history]" in block
    assert "refunds" in block.lower()


# --- retrieval -------------------------------------------------------------

def test_index_ranks_short_on_topic_doc_first():
    index = KnowledgeIndex()
    index.add(Document(doc_id="long", kind="knowledge",
                       text=" ".join(["filler"] * 40 + ["refund", "policy"])))
    index.add(Document(doc_id="short", kind="knowledge",
                       text="refund policy returns within 30 days"))
    hits = index.search("refund policy")
    assert hits[0].document.doc_id == "short"


def test_index_kind_filter_and_remove():
    index = KnowledgeIndex()
    index.add(Document(doc_id="t1", kind="tool", text="calculator tool math"))
    index.add(Document(doc_id="k1", kind="knowledge", text="calculator math guide"))
    assert [h.document.doc_id for h in index.search("calculator", kind="tool")] == ["t1"]
    assert index.remove("t1") is True
    assert index.search("calculator", kind="tool") == []
    assert index.remove("t1") is False


def test_index_empty_query_returns_nothing():
    assert KnowledgeIndex().search("") == []


# --- governance ------------------------------------------------------------

def _ctx(scopes=(), tenant="t1"):
    return TenantContext(tenant_id=tenant, principal="agent:demo",
                         scopes=frozenset(scopes))


def test_deny_by_default_with_no_policies():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="echo", description="echo",
                               fn=lambda text: text))
    with pytest.raises(PermissionError, match="deny-by-default"):
        registry.call("echo", _ctx(), resource_tenant="t1", text="hi")


def test_allow_policy_permits_scoped_tool():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="calc", description="calc",
                               required_scopes=frozenset({"tools:calc"}),
                               fn=lambda expression: 42.0))
    registry.policies.add(Policy(name="allow-calc", effect="allow", tool="calc"))
    assert registry.call("calc", _ctx(scopes={"tools:calc"}),
                         resource_tenant="t1", expression="1+1") == 42.0


def test_missing_scope_denies_before_policy():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="calc", description="calc",
                               required_scopes=frozenset({"tools:calc"}),
                               fn=lambda expression: 42.0))
    registry.policies.add(Policy(name="allow-calc", effect="allow", tool="calc"))
    with pytest.raises(PermissionError, match="missing scopes"):
        registry.call("calc", _ctx(), resource_tenant="t1", expression="1+1")


def test_deny_policy_beats_allow_policy():
    engine_policies = ToolRegistry()
    engine_policies.register(ToolSpec(name="export_data", description="export",
                                      fn=lambda: "data"))
    engine_policies.policies.add(Policy(name="allow-all", effect="allow"))
    engine_policies.policies.add(
        Policy(name="no-export", effect="deny", tool="export_data"))
    with pytest.raises(PermissionError, match="denied by policy no-export"):
        engine_policies.call("export_data", _ctx(), resource_tenant="t1")


def test_cross_tenant_call_denied():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="echo", description="echo",
                               fn=lambda text: text))
    registry.policies.add(Policy(name="allow-all", effect="allow"))
    with pytest.raises(PermissionError, match="cross-tenant"):
        registry.call("echo", _ctx(tenant="t1"), resource_tenant="t2", text="hi")


def test_unknown_tool_denied_and_audit_log_records_decisions():
    registry = ToolRegistry()
    registry.policies.add(Policy(name="allow-all", effect="allow"))
    with pytest.raises(PermissionError, match="unknown tool"):
        registry.call("nope", _ctx(), resource_tenant="t1")
    registry.register(ToolSpec(name="echo", description="echo",
                               fn=lambda text: text))
    registry.call("echo", _ctx(), resource_tenant="t1", text="hi")
    assert len(registry.policies.audit_log) == 1
    assert registry.policies.audit_log[0]["allowed"] is True


# --- SDK / CLI -------------------------------------------------------------

def test_engine_demo_agent_runs_end_to_end():
    engine = build_engine()
    result = engine.run("demo", context={"question": "refund policy"})
    assert result.ok
    assert result.values()["calculate"] == 42.0
    assert "kb-refund-policy" in result.values()["retrieve"]
    assert len(engine.memory.working) == 5  # 2 seeded + 3 step traces


def test_engine_rejects_unscoped_calculator_call():
    engine = Engine(tenant_id="t1", principal="agent:plain", scopes=[])
    engine.grant(Policy(name="allow-calc", effect="allow", tool="calculator"))
    with pytest.raises(PermissionError, match="missing scopes"):
        engine.call_tool("calculator", expression="1+1")


def test_engine_unknown_agent_raises():
    with pytest.raises(ValueError, match="unknown agent"):
        build_engine().run("no-such-agent")


def test_cli_list_tools(capsys):
    assert cli_main(["list-tools"]) == 0
    assert "calculator" in capsys.readouterr().out


def test_cli_run_demo(capsys):
    assert cli_main(["run", "demo", "--question", "refund policy"]) == 0
    out = capsys.readouterr().out
    assert '"status": "completed"' in out


def test_cli_search_finds_refund_doc(capsys):
    assert cli_main(["search", "refund policy"]) == 0
    assert "kb-refund-policy" in capsys.readouterr().out


def test_demo_steps_registered_on_engine():
    engine = Engine(tenant_id="t1", principal="agent:x", scopes=["tools:calc"])
    engine.grant(Policy(name="allow-calc", effect="allow", tool="calculator"))
    engine.grant(Policy(name="allow-echo", effect="allow", tool="echo"))
    engine.register_agent("demo", demo_agent_steps(engine))
    assert engine.agent_names() == ["demo"]
