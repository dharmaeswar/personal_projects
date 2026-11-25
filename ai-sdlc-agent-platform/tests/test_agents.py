from conftest import make_graph

from sdlc_agents.agents import (
    CodeGenAgent, ReleaseAgent, ReviewAgent, TestAgent, Ticket, build_tool_server,
    run_sdlc,
)
from sdlc_agents.pipeline import DIFFS, MODELS, PATCHED_SOURCES
from sdlc_agents.routing import ModelRouter

REPO = {"billing.py": "average parse_int charge billing totals"}


def _router():
    return ModelRouter(MODELS)


def test_codegen_generates_parsing_patch():
    tools = build_tool_server(REPO)
    ticket = Ticket("SDLC-101", "Fix average off-by-one in billing totals",
                    "average", "off_by_one", ["billing.py"])
    result = CodeGenAgent().run(ticket, make_graph(), tools, _router())
    assert result.passed
    assert "average" in result.summary
    assert tools.totals()["calls"] == 2  # read_file + open_pr


def test_codegen_fails_when_grounding_misses():
    tools = build_tool_server(REPO)
    ticket = Ticket("SDLC-999", "Fix refund webhook retry", "refund_webhook",
                    "off_by_one", ["billing.py"])
    result = CodeGenAgent().run(ticket, make_graph(), tools, _router())
    assert not result.passed


def test_review_blocks_on_secret_and_eval():
    diff = {"billing.py": ["password = 'hunter2'", "x = eval(user_input)"]}
    result = ReviewAgent().run(
        Ticket("SDLC-101", "t", "average", "off_by_one", ["billing.py"]),
        diff, _router())
    assert not result.passed
    assert result.artifacts["blocking"] == 2


def test_review_passes_clean_diff_and_counts_subagents():
    diff = {"billing.py": ["    return total // count"], "test_billing.py": ["assert average(10, 2) == 5"]}
    result = ReviewAgent().run(
        Ticket("SDLC-101", "t", "average", "off_by_one", ["billing.py"]),
        diff, _router())
    assert result.passed
    assert result.artifacts["subagents"] == 2


def test_testgen_runs_generated_cases():
    tools = build_tool_server(REPO)
    ticket = Ticket("SDLC-101", "Fix average off-by-one", "average", "off_by_one", ["billing.py"])
    result = TestAgent().run(ticket, PATCHED_SOURCES["off_by_one"], tools, _router())
    assert result.passed
    assert result.artifacts["cases"] == 3


def test_testgen_catches_wrong_patch():
    tools = build_tool_server(REPO)
    ticket = Ticket("SDLC-101", "Fix average off-by-one", "average", "off_by_one", ["billing.py"])
    wrong = "def average(total, count):\n    return total // (count + 1) if count else 0\n"
    result = TestAgent().run(ticket, wrong, tools, _router())
    assert not result.passed
    assert result.artifacts["failures"] == 2


def test_release_blocked_when_review_fails():
    from sdlc_agents.agents import StageResult
    stages = [
        StageResult("codegen", True, "ok"),
        StageResult("review", False, "blocking finding"),
        StageResult("testgen", True, "ok"),
    ]
    result = ReleaseAgent().run(
        Ticket("SDLC-101", "t", "average", "off_by_one", ["billing.py"]),
        stages, _router())
    assert not result.passed
    assert "review clean" in result.summary


def test_full_sdlc_run_all_stages_pass():
    tools = build_tool_server(REPO)
    ticket = Ticket("SDLC-101", "Fix average off-by-one in billing totals",
                    "average", "off_by_one", ["billing.py"])
    results = run_sdlc(ticket, make_graph(), tools, _router(),
                       DIFFS["SDLC-101"], PATCHED_SOURCES["off_by_one"])
    assert [r.stage for r in results] == ["codegen", "review", "testgen", "release"]
    assert all(r.passed for r in results)
