"""AI-agent tool surface: the workbench as tools an agent can call.

A stdio JSON-RPC 2.0 server (MCP-style) exposing the workbench to AI
coding tools and agents — the "build products for AI and agent use
cases" half of the job. An agent can list ideas, scaffold a prototype,
submit feedback, and read metrics without touching the code. The server
only runs the fixed tool handlers below, so a tool call can never write
arbitrary state or run arbitrary code.
"""

from __future__ import annotations

import json
import sys

from .feedback import decide
from .ideas import IdeaStore
from .pipeline import FeedbackPipeline
from .scaffold import PrototypeStore


class Workbench:
    """One workbench: the stores plus the tool handlers that use them."""

    def __init__(self):
        self.ideas = IdeaStore()
        self.prototypes = PrototypeStore()
        self.pipeline = FeedbackPipeline()

    def tool_list_ideas(self, params):
        status = params.get("status") if isinstance(params, dict) else None
        return [{"slug": i.slug, "title": i.title, "status": i.status}
                for i in self.ideas.list(status=status)]

    def tool_scaffold_prototype(self, params):
        slug = params.get("idea_slug")
        idea = self.ideas.get(slug)
        if idea is None:
            raise ValueError(f"unknown idea {slug!r}")
        proto = self.prototypes.scaffold(idea, build_minutes=int(params.get("build_minutes", 120)))
        self.ideas.set_status(slug, "prototyping")
        return {"slug": proto.slug, "status": proto.status,
                "api_routes": proto.api_routes,
                "pipeline_stages": proto.pipeline_stages,
                "frontend_page": proto.frontend_page}

    def tool_submit_feedback(self, params):
        result = self.pipeline.ingest(params if isinstance(params, dict) else {})
        return {"result": result}

    def tool_prototype_metrics(self, params):
        slug = params.get("prototype_slug")
        metrics = self.pipeline.metrics(slug)
        if metrics is None:
            return {"prototype_slug": slug, "count": 0, "decision": "not_enough_data",
                    "reason": "no feedback yet — keep testing with real users"}
        decision, reason = decide(metrics)
        return {**metrics, "decision": decision, "reason": reason}

    def handle(self, request):
        """Handle one JSON-RPC 2.0 request dict; return the response dict."""
        method = request.get("method")
        params = request.get("params") or {}
        req_id = request.get("id")
        tools = {
            "list_ideas": self.tool_list_ideas,
            "scaffold_prototype": self.tool_scaffold_prototype,
            "submit_feedback": self.tool_submit_feedback,
            "prototype_metrics": self.tool_prototype_metrics,
        }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [
                {"name": "list_ideas", "description": "List idea briefs, optionally by status"},
                {"name": "scaffold_prototype", "description": "Scaffold a working prototype from an idea brief"},
                {"name": "submit_feedback", "description": "Submit one user feedback event for a prototype"},
                {"name": "prototype_metrics", "description": "Feedback metrics and iterate/pivot/kill decision for a prototype"},
            ]}}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in tools:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"unknown tool {name!r}"}}
            try:
                result = tools[name](args)
            except (ValueError, TypeError, KeyError) as exc:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32602, "message": str(exc)}}
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result)}]}}
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"unknown method {method!r}"}}


def main():
    workbench = Workbench()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(workbench.handle(request)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
