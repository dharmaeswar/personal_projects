"""Stdlib HTTP API for the voice catalog + evaluation service.

Endpoints (all JSON unless noted):
  GET  /                        dashboard page (HTML)
  GET  /api/voices?q=&language=&style=&status=
  POST /api/voices             {"name","language","style_tags","clone_source","status"}
  GET  /api/voices/<id>
  POST /api/voices/<id>/versions   {"version","note","created_by"}
  POST /api/voices/<id>/evals     {"version","intelligibility","similarity","latency_ms","coverage"}
  GET  /api/voices/<id>/evals
  GET  /api/analytics

Usage: python -m voice_catalog   (serves http://127.0.0.1:8000)
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from voice_catalog.evaluation import EvalResult
from voice_catalog.service import EvalHistory, analytics_summary, run_eval
from voice_catalog.store import Store, VoiceStatus

STORE = Store()
HISTORY = EvalHistory()


def _send(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep demo output quiet
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            if path == "/":
                self._dashboard()
            elif path == "/api/voices":
                voices = STORE.list_voices(
                    query=query.get("q"),
                    language=query.get("language"),
                    style=query.get("style"),
                    status=query.get("status"),
                )
                _send(self, 200, [v.to_dict() for v in voices])
            elif path == "/api/analytics":
                _send(self, 200, analytics_summary(STORE, HISTORY))
            elif m := re.fullmatch(r"/api/voices/(\d+)", path):
                _send(self, 200, STORE.get_voice(int(m.group(1))).to_dict())
            elif m := re.fullmatch(r"/api/voices/(\d+)/evals", path):
                runs = HISTORY.for_voice(int(m.group(1)))
                _send(self, 200, [r.to_dict() for r in runs])
            else:
                _send(self, 404, {"error": "not found"})
        except (KeyError, ValueError) as exc:
            _send(self, 404 if isinstance(exc, KeyError) else 400, {"error": str(exc)})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = _read_json(self)
            if path == "/api/voices":
                voice = STORE.register_voice(
                    name=body.get("name", ""),
                    language=body.get("language", ""),
                    style_tags=body.get("style_tags") or [],
                    clone_source=body.get("clone_source", "recording"),
                    status=body.get("status", VoiceStatus.DRAFT.value),
                )
                _send(self, 201, voice.to_dict())
            elif m := re.fullmatch(r"/api/voices/(\d+)/versions", path):
                version = STORE.add_version(
                    int(m.group(1)),
                    body.get("version", ""),
                    note=body.get("note", ""),
                    created_by=body.get("created_by", ""),
                )
                _send(self, 201, {"version": version.version, "note": version.note})
            elif m := re.fullmatch(r"/api/voices/(\d+)/evals", path):
                for field in ("version", "intelligibility", "similarity", "latency_ms", "coverage"):
                    if field not in body:
                        raise ValueError(f"missing field: {field}")
                result: EvalResult = run_eval(
                    STORE,
                    HISTORY,
                    int(m.group(1)),
                    body["version"],
                    float(body["intelligibility"]),
                    float(body["similarity"]),
                    float(body["latency_ms"]),
                    float(body["coverage"]),
                )
                _send(self, 201, result.to_dict())
            else:
                _send(self, 404, {"error": "not found"})
        except (KeyError, ValueError) as exc:
            _send(self, 404 if isinstance(exc, KeyError) else 400, {"error": str(exc)})

    def _dashboard(self):
        summary = analytics_summary(STORE, HISTORY)
        rows = "".join(
            f"<tr><td>{v.name}</td><td>{v.language}</td><td>{', '.join(v.style_tags)}</td>"
            f"<td>{v.status.value}</td></tr>"
            for v in STORE.list_voices()
        )
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Voice Catalog</title></head><body>
<h1>Voice Catalog &amp; Evaluation</h1>
<p>Voices: {summary['voices']} &middot; active: {summary['active']} &middot;
quarantined: {summary['quarantined']} &middot; eval runs: {summary['eval_runs']} &middot;
pass rate: {summary['pass_rate']} &middot; mean composite: {summary['mean_composite']}</p>
<table border="1"><tr><th>Name</th><th>Language</th><th>Styles</th><th>Status</th></tr>
{rows}</table></body></html>"""
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(port: int = 8000) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"voice catalog serving on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
