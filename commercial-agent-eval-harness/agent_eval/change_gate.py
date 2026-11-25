"""AI-generated-code change gate (added Nov 25, 2026).

Compile/test/evaluate pipeline for AI-generated changes to a large
codebase — the gate an Agentic AI engineering team runs before an agent's
change can ship: compile check (real Python ``compile``), static
analysis, style checks, safety checks, performance gates, a test
requirement, retrieval-context coverage, and a code-review score.

Every check is deterministic and rule-based, so every eval is
reproducible with no model API calls. All sample changes are synthetic
seeded code; nothing here is a claim about any real firm or codebase.
"""

from __future__ import annotations

import ast
import re

# Gate budgets. A change fails the gate when any stage fails; the review
# score is a summary, not a substitute for the stage verdicts.
MAX_LINE_LENGTH = 120
MAX_ADDED_LINES = 500
MAX_ADDED_LINES_PER_FILE = 300
MAX_HOT_PATH_LOOP_DEPTH = 2
MAX_FUNCTION_LINES = 60
MIN_REVIEW_SCORE = 70

# Score deductions per failed stage (score starts at 100).
DEDUCTIONS = {
    "compile": 40,
    "safety": 30,
    "tests": 20,
    "performance": 15,
    "static-analysis": 10,
    "retrieval-context": 10,
    "style": 5,
}

# Safety patterns scanned as text (regex, case-insensitive where noted).
SECRET_PATTERN = re.compile(
    r"(password|passwd|api[_-]?key|secret|token)\s*=\s*[\"'][^\"']+[\"']",
    re.IGNORECASE)
SHELL_PATTERN = re.compile(r"shell\s*=\s*True")
BANNED_CALLS = {"eval", "exec"}
BANNED_ATTRS = {("os", "system"), ("os", "popen"), ("pickle", "loads"),
                ("subprocess", "call"), ("subprocess", "Popen")}


class ChangedFile:
    """One file in a proposed change: path, new content, hot-path flag."""

    def __init__(self, path, content, hot_path=False):
        self.path = path
        self.content = content
        self.hot_path = hot_path

    @property
    def added_lines(self):
        return len(self.content.splitlines())


class CodeChange:
    """A proposed change: files, claimed test run, retrieval context.

    ``tests_run`` is (passed, total) for the test run the agent claims.
    ``retrieval_context`` is the list of context snippets the agent was
    given (each a dict with ``source`` and ``snippet``); every changed
    file should be covered by at least one snippet.
    """

    def __init__(self, change_id, author, files, tests_run=(0, 0),
                 retrieval_context=None):
        self.change_id = change_id
        self.author = author
        self.files = list(files)
        self.tests_run = tests_run
        self.retrieval_context = list(retrieval_context or [])


class GateCheck:
    def __init__(self, stage, passed, detail=""):
        self.stage = stage
        self.passed = passed
        self.detail = detail

    def as_dict(self):
        return {"stage": self.stage, "passed": self.passed,
                "detail": self.detail}


class GateVerdict:
    def __init__(self, change, checks):
        self.change_id = change.change_id
        self.author = change.author
        self.checks = checks
        self.failures = [c.detail for c in checks if not c.passed]
        self.score = max(
            0, 100 - sum(DEDUCTIONS.get(c.stage, 5) for c in checks
                         if not c.passed))
        self.passed = not self.failures and self.score >= MIN_REVIEW_SCORE

    def as_dict(self):
        return {"change_id": self.change_id, "author": self.author,
                "passed": self.passed, "score": self.score,
                "failures": self.failures,
                "checks": [c.as_dict() for c in self.checks]}


def _check_compile(change):
    problems = []
    for f in change.files:
        try:
            compile(f.content, f.path, "exec")
        except SyntaxError as exc:
            problems.append(f"{f.path}: {exc.msg} (line {exc.lineno})")
    if problems:
        return GateCheck("compile", False, "; ".join(problems))
    return GateCheck("compile", True,
                     f"{len(change.files)} file(s) compile cleanly")


def _max_loop_depth(tree):
    """Deepest nesting of for/while loops in a parsed module."""
    worst = [0]

    def walk(node, depth):
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            depth += 1
            worst[0] = max(worst[0], depth)
        for child in ast.iter_child_nodes(node):
            walk(child, depth)

    walk(tree, 0)
    return worst[0]


def _check_static_analysis(change):
    problems = []
    for f in change.files:
        try:
            tree = ast.parse(f.content)
        except SyntaxError:
            continue  # compile stage already reports this
        lines = f.content.splitlines()
        # Unused imports: imported name never used outside its import line.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = (alias.asname or alias.name).split(".")[0]
                    uses = sum(1 for ln in lines
                               if re.search(r"\b" + re.escape(name) + r"\b", ln))
                    imports = sum(1 for ln in lines
                                  if ln.strip().startswith("import ")
                                  and name in ln)
                    if uses <= imports:
                        problems.append(f"{f.path}: unused import {name}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    uses = sum(1 for ln in lines
                               if re.search(r"\b" + re.escape(name) + r"\b", ln))
                    if uses <= 1:
                        problems.append(f"{f.path}: unused import {name}")
        # Over-long functions.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                if span > MAX_FUNCTION_LINES:
                    problems.append(
                        f"{f.path}: function {node.name} is {span} lines "
                        f"(max {MAX_FUNCTION_LINES})")
    if problems:
        return GateCheck("static-analysis", False, "; ".join(problems))
    return GateCheck("static-analysis", True, "no unused imports or "
                     "over-long functions")


def _check_style(change):
    problems = []
    for f in change.files:
        for i, line in enumerate(f.content.splitlines(), 1):
            if len(line) > MAX_LINE_LENGTH:
                problems.append(f"{f.path}:{i}: line is {len(line)} chars "
                                f"(max {MAX_LINE_LENGTH})")
            if line != line.rstrip():
                problems.append(f"{f.path}:{i}: trailing whitespace")
            if line.startswith("\t") or "\t" in line[:len(line) - len(line.lstrip())]:
                problems.append(f"{f.path}:{i}: tab indentation")
    if problems:
        return GateCheck("style", False, "; ".join(problems[:5]))
    return GateCheck("style", True, "line length, whitespace and "
                     "indentation clean")


def _check_safety(change):
    problems = []
    for f in change.files:
        if SECRET_PATTERN.search(f.content):
            problems.append(f"{f.path}: hardcoded credential or secret")
        if SHELL_PATTERN.search(f.content):
            problems.append(f"{f.path}: subprocess shell=True")
        try:
            tree = ast.parse(f.content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                    problems.append(f"{f.path}: banned call {func.id}()")
                elif isinstance(func, ast.Attribute):
                    base = func.value
                    if isinstance(base, ast.Name) and \
                            (base.id, func.attr) in BANNED_ATTRS:
                        problems.append(
                            f"{f.path}: banned call {base.id}.{func.attr}()")
    if problems:
        return GateCheck("safety", False, "; ".join(problems))
    return GateCheck("safety", True, "no banned calls, shell use or "
                     "hardcoded secrets")


def _check_performance(change):
    problems = []
    total = sum(f.added_lines for f in change.files)
    if total > MAX_ADDED_LINES:
        problems.append(f"change adds {total} lines (max {MAX_ADDED_LINES})")
    for f in change.files:
        if f.added_lines > MAX_ADDED_LINES_PER_FILE:
            problems.append(f"{f.path}: adds {f.added_lines} lines "
                            f"(max {MAX_ADDED_LINES_PER_FILE})")
        if f.hot_path:
            try:
                depth = _max_loop_depth(ast.parse(f.content))
            except SyntaxError:
                continue
            if depth > MAX_HOT_PATH_LOOP_DEPTH:
                problems.append(
                    f"{f.path}: hot path loop depth {depth} "
                    f"(max {MAX_HOT_PATH_LOOP_DEPTH})")
    if problems:
        return GateCheck("performance", False, "; ".join(problems))
    return GateCheck("performance", True,
                     f"{total} added line(s) within budgets; hot-path "
                     "loop depth within budget")


def _check_tests(change):
    passed, total = change.tests_run
    if total == 0:
        return GateCheck("tests", False, "no tests run for this change")
    if passed < total:
        return GateCheck("tests", False,
                         f"{passed}/{total} tests pass")
    return GateCheck("tests", True, f"{passed}/{total} tests pass")


def _check_retrieval_context(change):
    """Every changed file must be covered by the retrieval context given
    to the agent: at least one snippet must name the file's module stem.
    A change the agent made without reading the relevant code is not
    auditable, however clean it looks."""
    uncovered = []
    for f in change.files:
        stem = f.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        covered = any(stem in (c.get("source", "") + c.get("snippet", ""))
                      for c in change.retrieval_context)
        if not covered:
            uncovered.append(f.path)
    if uncovered:
        return GateCheck("retrieval-context", False,
                         "no retrieved context covers: "
                         + ", ".join(uncovered))
    return GateCheck("retrieval-context", True,
                     f"{len(change.files)} file(s) covered by retrieved "
                     "context")


def gate_change(change):
    """Run the full compile/test/evaluate pipeline on one change."""
    if not change.files:
        return GateVerdict(change, [GateCheck(
            "compile", False, "empty change: no files")])
    checks = [
        _check_compile(change),
        _check_static_analysis(change),
        _check_style(change),
        _check_safety(change),
        _check_performance(change),
        _check_tests(change),
        _check_retrieval_context(change),
    ]
    return GateVerdict(change, checks)


def build_sample_changes(seed=25):
    """Seeded synthetic changes: one clean agent change and four that
    each fail a different gate stage. Deterministic; no real code."""
    clean = CodeChange(
        "CHG-101", "agent",
        [ChangedFile("pricing/engine.py",
                     "def discount(price, rate):\n"
                     "    \"\"\"Apply a discount rate to a price.\"\"\"\n"
                     "    return round(price * (1 - rate), 2)\n",
                     hot_path=True)],
        tests_run=(4, 4),
        retrieval_context=[{"source": "pricing/engine.py",
                            "snippet": "engine.py holds the pricing "
                            "helpers used by the order path"}])
    syntax = CodeChange(
        "CHG-102", "agent",
        [ChangedFile("pricing/engine.py",
                     "def discount(price, rate)\n"
                     "    return round(price * (1 - rate), 2)\n")],
        tests_run=(0, 0),
        retrieval_context=[{"source": "pricing/engine.py",
                            "snippet": "engine.py pricing helpers"}])
    unsafe = CodeChange(
        "CHG-103", "agent",
        [ChangedFile("auth/session.py",
                     "password = \"hunter2\"\n\n\n"
                     "def run(cmd):\n"
                     "    return eval(cmd)\n")],
        tests_run=(2, 2),
        retrieval_context=[{"source": "auth/session.py",
                            "snippet": "session.py manages auth "
                            "sessions"}])
    slow = CodeChange(
        "CHG-104", "agent",
        [ChangedFile("pricing/engine.py",
                     "def slow_total(orders):\n"
                     "    total = 0\n"
                     "    for order in orders:\n"
                     "        for line in order:\n"
                     "            for part in line:\n"
                     "                total += part\n"
                     "    return total\n",
                     hot_path=True)],
        tests_run=(3, 3),
        retrieval_context=[{"source": "pricing/engine.py",
                            "snippet": "engine.py pricing helpers"}])
    untested = CodeChange(
        "CHG-105", "human",
        [ChangedFile("reporting/daily.py",
                     "def summarise(rows):\n"
                     "    \"\"\"Count rows by status.\"\"\"\n"
                     "    out = {}\n"
                     "    for row in rows:\n"
                     "        out[row[\"status\"]] = out.get(row[\"status\"], 0) + 1\n"
                     "    return out\n")],
        tests_run=(1, 3),
        retrieval_context=[])
    return [clean, syntax, unsafe, slow, untested]


def run_change_gate_eval(changes=None):
    """Gate every sample change; return the report dict."""
    changes = changes if changes is not None else build_sample_changes()
    verdicts = [gate_change(c) for c in changes]
    passed = sum(1 for v in verdicts if v.passed)
    return {
        "changes": [v.as_dict() for v in verdicts],
        "total": len(verdicts),
        "passed": passed,
        "failed": len(verdicts) - passed,
        "pass_rate": passed / len(verdicts) if verdicts else 0.0,
        "verdict": "PASS" if passed == len(verdicts) else "FAIL",
    }
