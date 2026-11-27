"""Low-latency serving API (stdlib http.server, JSON).

GET  /signals/<user_id>  merged, consented signals for a user
POST /events             ingest one raw event (validated, quarantined
                         on failure, never stored unvalidated)
GET  /health             store + pipeline state

Consent is enforced at serve time and every serve is audit-logged.
Latency here is in-process (local JSON store), not a production SLA.
"""
from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .batch import build_batch_signals, build_user_context
from .ingest import ingest_batch
from .models import Consent
from .privacy import filter_by_consent
from .realtime import merge_signals, realtime_signals
from .store import Store


class SignalServer:
    def __init__(self, store: Store, consents: dict[str, Consent],
                 run_id: str = "serve", now: datetime | None = None):
        self.store = store
        self.consents = consents
        self.run_id = run_id
        self.now = now or datetime.now()

    def signals_for_user(self, user_id: str) -> tuple[list[dict], list[str]]:
        """Return (served signals as dicts, withheld categories)."""
        consent = self.consents.get(user_id, Consent(user_id=user_id))
        events = self.store.events()
        profile = build_user_context(user_id, events, consent, self.run_id, self.now)
        batch = build_batch_signals(profile, self.run_id)
        realtime = realtime_signals(user_id, events, consent, self.run_id, self.now)
        merged = merge_signals(batch, realtime)
        # Withheld = categories the user has events in but did not consent to.
        from .privacy import category_of
        withheld = sorted({category_of(e.event_type) for e in events
                           if e.user_id == user_id and not consent.allows(category_of(e.event_type))})
        served = filter_by_consent(merged, consent)
        self.store.audit({"action": "serve", "user_id": user_id,
                          "served": len(served), "withheld_categories": withheld,
                          "at": self.now.isoformat()})
        return [{"signal_type": s.signal_type, "value": s.value,
                 "score": s.score, "source": s.source} for s in served], withheld

    def ingest_one(self, raw: dict):
        accepted, quarantined = ingest_batch([raw], self.store.event_ids(), now=self.now)
        if accepted:
            self.store.add_events(accepted)
        return accepted, quarantined

    def health(self) -> dict:
        return {"events": len(self.store.data["events"]),
                "profiles": len(self.store.data["profiles"]),
                "signals": len(self.store.data["signals"]),
                "audit_entries": len(self.store.data["audit"])}


def make_handler(server: SignalServer):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, server.health())
            elif self.path.startswith("/signals/"):
                user_id = self.path.split("/signals/")[1].split("/")[0]
                served, withheld = server.signals_for_user(user_id)
                self._send(200, {"user_id": user_id, "signals": served,
                                 "withheld_categories": withheld})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/events":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = json.loads(self.rfile.read(length) or b"{}")
            accepted, quarantined = server.ingest_one(raw)
            self._send(200 if accepted else 400,
                       {"accepted": len(accepted),
                        "quarantined": [q["reasons"] for q in quarantined]})

        def log_message(self, *args):  # keep test output clean
            pass

    return Handler


def serve(store: Store, consents: dict, host: str = "127.0.0.1", port: int = 8000):
    httpd = ThreadingHTTPServer((host, port), make_handler(SignalServer(store, consents)))
    print(f"Serving on http://{host}:{port}  (GET /signals/<user_id>, GET /health)")
    httpd.serve_forever()
