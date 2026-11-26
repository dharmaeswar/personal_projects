"""REST API for the marketing RAG service, standard library only.

Endpoints
- GET  /health      -> {"status": "ok"}
- GET  /campaigns   -> list of campaigns with spend, CPA and ROI
- POST /ask         -> {"question": "..."} -> answer, citations, validation
- POST /evaluate    -> runs the evaluation harness and returns the report

Run: python run_server.py  (default port 8000)
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agents import BudgetAgent
from .corpus import CAMPAIGNS
from .evaluation import run_evaluation
from .service import MarketingRagService

SERVICE = MarketingRagService()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path in ("/health", "/health/"):
            self._send_json(200, {"status": "ok"})
        elif self.path in ("/campaigns", "/campaigns/"):
            stats = [BudgetAgent.campaign_stats(c) for c in CAMPAIGNS]
            self._send_json(200, {"campaigns": stats})
        else:
            self._send_json(404, {"error": f"unknown path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path in ("/ask", "/ask/"):
            payload = self._read_json()
            question = payload.get("question", "")
            if not isinstance(question, str) or not question.strip():
                self._send_json(400, {"error": "question is required"})
                return
            self._send_json(200, SERVICE.ask(question))
        elif self.path in ("/evaluate", "/evaluate/"):
            self._send_json(200, run_evaluation(SERVICE))
        else:
            self._send_json(404, {"error": f"unknown path: {self.path}"})

    def log_message(self, *args) -> None:  # keep test output clean
        pass


def run_server(port: int = 8000) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Marketing RAG service listening on http://127.0.0.1:{port}")
    print("Endpoints: GET /health, GET /campaigns, POST /ask, POST /evaluate")
    server.serve_forever()
    return server
