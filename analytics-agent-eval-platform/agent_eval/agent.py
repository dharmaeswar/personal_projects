"""The analytics agent: plan, retrieve context, call tools, validate, report.

Workflow for one question, mirroring the Reddit AI & Science Platform role:
1. Plan — name the steps (context, SQL, execution, validation, summary).
2. Context retrieval — describe the dataset so the SQL is grounded in the
   real schema, not a guessed one.
3. Structured tool calls — text-to-SQL, then sandboxed execution, each
   through the MCP-style tool server with tracing.
4. Execution state — the run keeps explicit state (planned, running,
   validated, complete / incomplete) so a failure is visible, not silent.
5. Result validation — empty or malformed results fail validation.
6. Failure handling — one repair retry (strip a trailing semicolon, the
   most common model slip); after that the task is marked incomplete with
   the reason, never answered from invented data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tools import ToolServer


@dataclass
class AgentResult:
    question: str
    status: str  # "complete" or "incomplete"
    plan: list[str] = field(default_factory=list)
    sql: str | None = None
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    summary: str | None = None
    provenance: dict = field(default_factory=dict)
    failure_reason: str | None = None
    tool_calls: list = field(default_factory=list)


class AnalyticsAgent:
    """Multi-step analytics agent over the sandboxed dataset."""

    def __init__(self, tools: ToolServer):
        self.tools = tools

    def answer(self, question: str) -> AgentResult:
        result = AgentResult(question=question, status="incomplete")
        trace_start = len(self.tools.trace)
        result.plan = [
            "retrieve dataset context",
            "translate question to SQL",
            "execute SQL in the sandbox",
            "validate the result",
            "summarize from the returned rows only",
        ]

        context = self.tools.call("describe_dataset", {})
        if not context.ok:
            result.failure_reason = f"context retrieval failed: {context.error}"
            return self._finish(result, trace_start)

        sql_call = self.tools.call("text_to_sql", {"question": question})
        if not sql_call.ok:
            result.failure_reason = (
                f"could not translate question to SQL: {sql_call.error}")
            return self._finish(result, trace_start)
        result.sql = sql_call.result["sql"]

        run = self.tools.call("run_query", {"sql": result.sql})
        if not run.ok:
            # One repair retry: strip a trailing semicolon and retry once.
            repaired = result.sql.strip().rstrip(";")
            if repaired != result.sql:
                result.sql = repaired
                run = self.tools.call("run_query", {"sql": repaired})
            if not run.ok:
                result.failure_reason = (
                    f"sandboxed execution failed: {run.error}")
                return self._finish(result, trace_start)
        result.columns = run.result["columns"]
        result.rows = run.result["rows"]
        result.provenance = run.result["provenance"]

        check = self.tools.call("validate_result", {
            "question": question,
            "columns": result.columns,
            "rows": result.rows,
        })
        if not check.ok or not check.result["valid"]:
            issues = check.result.get("issues", [check.error]) if check.ok \
                else [check.error]
            result.failure_reason = (
                "result validation failed: " + "; ".join(issues))
            return self._finish(result, trace_start)

        summary = self.tools.call("summarize", {
            "question": question,
            "columns": result.columns,
            "rows": result.rows,
        })
        if not summary.ok:
            result.failure_reason = f"summary failed: {summary.error}"
            return self._finish(result, trace_start)
        result.summary = summary.result["summary"]
        result.status = "complete"
        return self._finish(result, trace_start)

    def _finish(self, result: AgentResult, trace_start: int) -> AgentResult:
        # Only this question's tool calls, not earlier cases' traces.
        result.tool_calls = [
            {"tool": c.name, "ok": c.ok, "latency_ms": round(c.latency_ms, 2),
             "cost_usd": c.cost_usd, "error": c.error}
            for c in self.tools.trace[trace_start:]
        ]
        return result
