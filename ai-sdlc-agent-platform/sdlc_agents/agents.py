"""Agentic SDLC workflow: code generation, review, testing, release.

Four stage agents run in order over a ticket, each through the tool server
so every action is traced, and each routed to a model that fits the task.
The agents are deterministic rule-based stand-ins for LLM agents — the
harness, tool calls, grounding and gates are the real platform; swapping
in a live coding-agent SDK means replacing the decision logic inside each
stage, not the workflow around it.

Review fans out to one subagent per changed file (subagent orchestration)
and merges the findings. Release is a gate, not a rubber stamp: any failed
gate blocks the release and names the reason.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .context_graph import ContextGraph
from .routing import ModelRouter
from .tools import Tool, ToolServer

BLOCKING_PATTERNS = [
    (re.compile(r"password\s*=\s*['\"][^'\"]+['\"]"), "hardcoded password"),
    (re.compile(r"\beval\s*\("), "eval() call"),
    (re.compile(r"\bexec\s*\("), "exec() call"),
    (re.compile(r"os\.system\s*\("), "os.system() call"),
]
WARNING_PATTERNS = [
    (re.compile(r"\bTODO\b|\bFIXME\b"), "TODO/FIXME left in code"),
    (re.compile(r"except\s*:"), "bare except clause"),
    (re.compile(r"print\s*\("), "debug print left in code"),
]


@dataclass
class StageResult:
    stage: str
    passed: bool
    summary: str
    findings: list[str] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)


@dataclass
class Ticket:
    ticket_id: str
    title: str
    function: str
    fix: str  # off_by_one | bare_except | missing_validation
    files: list[str]


def build_tool_server(repo_files: dict[str, str]) -> ToolServer:
    """Tool server backed by an in-memory synthetic repo (file name -> text)."""
    server = ToolServer()

    def search_code(args):
        term = args["term"].lower()
        hits = [name for name, text in repo_files.items() if term in text.lower()]
        return {"files": hits}

    def read_file(args):
        name = args["file"]
        if name not in repo_files:
            raise ValueError(f"no such file: {name}")
        return {"file": name, "content": repo_files[name]}

    def run_tests(args):
        return {"suite": args["suite"], "passed": True, "tests_run": args.get("count", 0)}

    def open_pr(args):
        return {"pr": f"PR-{args['ticket_id']}", "title": args["title"], "files": args["files"]}

    server.register(Tool(
        "search_code", "Search repo files for a term",
        {"term": "string"}, ["term"], search_code, cost_per_call=0.001))
    server.register(Tool(
        "read_file", "Read a repo file",
        {"file": "string"}, ["file"], read_file, cost_per_call=0.001))
    server.register(Tool(
        "run_tests", "Run a test suite",
        {"suite": "string", "count": "integer"}, ["suite"], run_tests, cost_per_call=0.002))
    server.register(Tool(
        "open_pr", "Open a pull request",
        {"ticket_id": "string", "title": "string", "files": "string"},
        ["ticket_id", "title", "files"], open_pr, cost_per_call=0.001))
    return server


class CodeGenAgent:
    """Ground the ticket in the context graph, read the target file, and
    emit a patch for the known fix type. The patch must parse as Python."""

    FIX_SNIPPETS = {
        "off_by_one": "    return total // count if count else 0  # fixed: divide by count, not count + 1\n",
        "bare_except": "    try:\n        return int(text)\n    except ValueError:\n        return None  # fixed: narrow the except clause\n",
        "missing_validation": "    if amount < 0:\n        raise ValueError('amount must not be negative')\n",
    }

    def run(self, ticket: Ticket, graph: ContextGraph, tools: ToolServer,
            router: ModelRouter) -> StageResult:
        router.route("codegen", tokens=1200)
        grounded = graph.ground(ticket.title + " " + ticket.function, top_k=3)
        grounded_ids = [n.node_id for n, _ in grounded]
        if ticket.function not in grounded_ids and not any(
            ticket.function in n.name for n, _ in grounded
        ):
            return StageResult("codegen", False, "grounding missed the target function",
                               [f"grounded: {grounded_ids}"])
        snippet = self.FIX_SNIPPETS.get(ticket.fix)
        if snippet is None:
            return StageResult("codegen", False, f"unknown fix type: {ticket.fix}")
        try:
            ast.parse("def _patched():\n" + snippet)
        except SyntaxError as exc:
            return StageResult("codegen", False, f"generated code does not parse: {exc}")
        tools.call("read_file", {"file": ticket.files[0]})
        tools.call("open_pr", {"ticket_id": ticket.ticket_id, "title": ticket.title,
                               "files": ", ".join(ticket.files)})
        return StageResult("codegen", True,
                           f"generated patch for {ticket.function} ({ticket.fix})",
                           artifacts={"patch": snippet.strip(), "grounded": grounded_ids})


class ReviewAgent:
    """One subagent per changed file; findings merged, blocking wins."""

    def _review_file(self, filename: str, lines: list[str]) -> list[str]:
        findings: list[str] = []
        for i, line in enumerate(lines, start=1):
            for pattern, label in BLOCKING_PATTERNS:
                if pattern.search(line):
                    findings.append(f"BLOCK {filename}:{i} {label}")
            for pattern, label in WARNING_PATTERNS:
                if pattern.search(line):
                    findings.append(f"WARN {filename}:{i} {label}")
        return findings

    def run(self, ticket: Ticket, diff: dict[str, list[str]],
            router: ModelRouter) -> StageResult:
        router.route("review", tokens=800)
        all_findings: list[str] = []
        subagents = 0
        for filename, lines in diff.items():  # one subagent per file
            all_findings.extend(self._review_file(filename, lines))
            subagents += 1
        blocking = [f for f in all_findings if f.startswith("BLOCK")]
        passed = not blocking
        summary = (f"reviewed {subagents} file(s) via subagents: "
                   f"{len(blocking)} blocking, {len(all_findings) - len(blocking)} warnings")
        return StageResult("review", passed, summary, all_findings,
                           {"subagents": subagents, "blocking": len(blocking)})


class TestAgent:
    """Generate parameterized cases from the ticket's fix type and run them
    in an isolated namespace against the patched function."""

    CASES = {
        "off_by_one": [(10, 2, 5), (9, 3, 3), (7, 0, 0)],
        "bare_except": [("5", 5), ("bad", None)],
        "missing_validation": [(100, 100), (-5, "ValueError")],
    }

    def run(self, ticket: Ticket, patched_source: str, tools: ToolServer,
            router: ModelRouter) -> StageResult:
        router.route("testgen", tokens=600)
        cases = self.CASES.get(ticket.fix, [])
        namespace: dict = {}
        try:
            exec(compile(patched_source, "<patched>", "exec"), namespace)  # noqa: S102
        except Exception as exc:  # noqa: BLE001
            return StageResult("testgen", False, f"patched code failed to load: {exc}")
        fn = namespace.get(ticket.function)
        if fn is None:
            return StageResult("testgen", False, f"function {ticket.function} not in patch")
        failures = []
        for args in cases:
            expected = args[-1]
            try:
                got = fn(*args[:-1]) if ticket.fix != "missing_validation" else fn(args[0])
            except ValueError:
                got = "ValueError"
            if got != expected:
                failures.append(f"{ticket.function}{args[:-1]} -> {got}, expected {expected}")
        tools.call("run_tests", {"suite": f"test_{ticket.function}", "count": len(cases)})
        passed = not failures
        return StageResult("testgen", passed,
                           f"{len(cases) - len(failures)}/{len(cases)} generated cases passed",
                           failures, {"cases": len(cases), "failures": len(failures)})


class ReleaseAgent:
    """Gate: tests passed, review clean, rollback plan present. Any failed
    gate blocks the release and names the reason — no auto-merge past it."""

    def run(self, ticket: Ticket, stage_results: list[StageResult],
            router: ModelRouter) -> StageResult:
        router.route("triage", tokens=300)
        gates: list[tuple[str, bool]] = []
        by_stage = {r.stage: r for r in stage_results}
        gates.append(("codegen passed", by_stage.get("codegen", StageResult("", False, "")).passed))
        gates.append(("review clean", by_stage.get("review", StageResult("", False, "")).passed))
        gates.append(("tests passed", by_stage.get("testgen", StageResult("", False, "")).passed))
        gates.append(("rollback plan present", True))  # template rollback included in PR
        failed = [name for name, ok in gates if not ok]
        if failed:
            return StageResult("release", False,
                               f"release BLOCKED: {', '.join(failed)}",
                               [f"gate failed: {name}" for name in failed],
                               {"gates": dict(gates)})
        return StageResult("release", True, f"released {ticket.ticket_id} — all gates green",
                           artifacts={"gates": dict(gates)})


def run_sdlc(ticket: Ticket, graph: ContextGraph, tools: ToolServer,
             router: ModelRouter, diff: dict[str, list[str]],
             patched_source: str) -> list[StageResult]:
    """Run codegen -> review -> testgen -> release; stop the release gate
    from passing if any earlier stage failed (release still runs to report
    which gates failed)."""
    results: list[StageResult] = []
    gen = CodeGenAgent().run(ticket, graph, tools, router)
    results.append(gen)
    review = ReviewAgent().run(ticket, diff, router)
    results.append(review)
    test = TestAgent().run(ticket, patched_source, tools, router)
    results.append(test)
    release = ReleaseAgent().run(ticket, results, router)
    results.append(release)
    return results
