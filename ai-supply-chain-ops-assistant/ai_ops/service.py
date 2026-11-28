"""HTTP API + browser dashboard for the AI Supply Chain Ops Assistant.

Standard library only. Endpoints:
  GET  /            dashboard (HTML)
  GET  /health      {"status": "ok"}
  POST /ask         {"question": str} -> knowledge or analytics answer
  POST /workflows/draft-reorders   -> draft reorder tasks from signals
  POST /workflows/<id>/review      {"approve": bool, "reviewer": str}
  GET  /workflows   list tasks (optional ?status=draft)
  POST /eval        run the representative-task eval harness
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .analytics import answer as analytics_answer
from .evaluate import run_eval
from .knowledge import answer as knowledge_answer
from .workflows import WorkflowStore, draft_reorders, draft_transfer

STORE = WorkflowStore()

DASHBOARD = """<!doctype html>
<html><head><meta charset="utf-8"><title>AI Supply Chain Ops Assistant</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em}
input,button{font-size:1em;padding:.4em}input{width:70%}pre{background:#f4f4f4;padding:1em;white-space:pre-wrap}</style>
</head><body>
<h1>AI Supply Chain Ops Assistant</h1>
<p>Ask about runbooks or inventory data. Answers cite their sources; drafts need a human's approval.</p>
<input id="q" placeholder="e.g. How is the reorder point calculated?">
<button onclick="ask()">Ask</button>
<button onclick="runEval()">Run eval suite</button>
<button onclick="draft()">Draft reorders</button>
<pre id="out">Ready.</pre>
<script>
async function post(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{})});
  return r.json();
}
async function ask(){
  const q = document.getElementById('q').value;
  document.getElementById('out').textContent = JSON.stringify(await post('/ask', {question:q}), null, 2);
}
async function runEval(){ document.getElementById('out').textContent = JSON.stringify(await post('/eval', {}), null, 2); }
async function draft(){ document.getElementById('out').textContent = JSON.stringify(await post('/workflows/draft-reorders', {}), null, 2); }
</script>
</body></html>
"""


def ask(question):
    """Route a question: analytics keywords go to the data layer, the rest
    to the runbook knowledge base."""
    q = question.lower()
    if any(word in q for word in ("fill rate", "stockout", "cover", "low stock")):
        return {"source": "analytics", **analytics_answer(question)}
    return {"source": "knowledge", **knowledge_answer(question)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, DASHBOARD.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/health":
            self._send(200, {"status": "ok"})
        elif parsed.path == "/workflows":
            status = parse_qs(parsed.query).get("status", [None])[0]
            self._send(200, {"tasks": STORE.list_tasks(status)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "invalid JSON"})
            return
        if parsed.path == "/ask":
            question = body.get("question", "")
            if not question.strip():
                self._send(400, {"error": "question is required"})
                return
            self._send(200, ask(question))
        elif parsed.path == "/workflows/draft-reorders":
            tasks, created = draft_reorders(STORE)
            self._send(200, {"tasks": tasks, "created": created})
        elif parsed.path == "/workflows/draft-transfer":
            try:
                task = draft_transfer(
                    STORE, body["sku"], body["from_warehouse"],
                    body["to_warehouse"], int(body["units"]),
                )
            except (KeyError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
                return
            self._send(200, {"task": task})
        elif parsed.path.startswith("/workflows/") and parsed.path.endswith("/review"):
            task_id = parsed.path.split("/")[2]
            try:
                task = STORE.review(task_id, bool(body.get("approve")), body.get("reviewer", "operator"))
            except (KeyError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
                return
            self._send(200, {"task": task})
        elif parsed.path == "/eval":
            self._send(200, run_eval())
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):  # keep test output clean
        pass


def run_server(port=8080):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"AI Supply Chain Ops Assistant on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
