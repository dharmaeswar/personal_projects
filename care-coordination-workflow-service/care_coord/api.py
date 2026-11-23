"""Small HTTP API over the care-coordination service (stdlib only).

Routes (all JSON):
  GET  /health
  POST /care-plans                       {"patient_ref","title","goals"?,"request_key"?}
  GET  /care-plans                       list all plans
  GET  /care-plans/{id}                  plan + referrals + tasks + audit
  POST /care-plans/{id}/transition       {"status"}
  POST /care-plans/{id}/referrals        {"specialty","reason"?,"request_key"?}
  POST /referrals/{id}/transition        {"status"}
  POST /care-plans/{id}/tasks            {"title","assignee"?,"request_key"?}
  POST /tasks/{id}/transition            {"status"}
  GET  /audit                            full audit trail
  POST /outbox/process                   drain the outbox (demo handler logs events)

Run:  python3 run_demo.py --serve --port 8000
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .models import (
    CarePlan, Referral, Task, AuditEntry, Event,
    PlanStatus, ReferralStatus, TaskStatus,
)
from .service import (
    CareCoordinationService, InvalidTransitionError, NotFoundError, ValidationError,
)


def _to_jsonable(obj):
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "value"):  # enums
        return obj.value
    return obj


def make_handler(service: CareCoordinationService):
    delivered_log: list = []

    def demo_handler(event: Event):
        delivered_log.append({"type": event.event_type, "id": event.id})

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        def _send(self, status, payload):
            body = json.dumps(_to_jsonable(payload)).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")

        def _route(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            return self.command, parts

        def do_GET(self):
            _, parts = self._route()
            try:
                if parts == ["health"]:
                    return self._send(200, {"status": "ok"})
                if parts == ["care-plans"]:
                    return self._send(200, list(service.store.plans.values()))
                if len(parts) == 2 and parts[0] == "care-plans":
                    return self._send(200, service.plan_summary(parts[1]))
                if parts == ["audit"]:
                    return self._send(200, service.store.audit)
                if parts == ["outbox"]:
                    return self._send(200, service.store.pending_events())
                return self._send(404, {"error": "not found"})
            except NotFoundError as e:
                return self._send(404, {"error": f"not found: {e}"})

        def do_POST(self):
            _, parts = self._route()
            try:
                body = self._body()
                if parts == ["care-plans"]:
                    plan = service.create_care_plan(
                        body.get("patient_ref", ""), body.get("title", ""),
                        body.get("goals"), request_key=body.get("request_key"))
                    return self._send(201, plan)
                if len(parts) == 3 and parts[0] == "care-plans" and parts[2] == "transition":
                    plan = service.transition_plan(parts[1], body.get("status", ""))
                    return self._send(200, plan)
                if len(parts) == 3 and parts[0] == "care-plans" and parts[2] == "referrals":
                    ref = service.add_referral(parts[1], body.get("specialty", ""),
                                               body.get("reason", ""),
                                               request_key=body.get("request_key"))
                    return self._send(201, ref)
                if len(parts) == 3 and parts[0] == "referrals" and parts[2] == "transition":
                    ref = service.transition_referral(parts[1], body.get("status", ""))
                    return self._send(200, ref)
                if len(parts) == 3 and parts[0] == "care-plans" and parts[2] == "tasks":
                    task = service.create_task(parts[1], body.get("title", ""),
                                               body.get("assignee", ""),
                                               request_key=body.get("request_key"))
                    return self._send(201, task)
                if len(parts) == 3 and parts[0] == "tasks" and parts[2] == "transition":
                    task = service.transition_task(parts[1], body.get("status", ""))
                    return self._send(200, task)
                if parts == ["outbox", "process"]:
                    counts = service.process_outbox(demo_handler)
                    return self._send(200, {"counts": counts, "delivered": delivered_log})
                return self._send(404, {"error": "not found"})
            except NotFoundError as e:
                return self._send(404, {"error": f"not found: {e}"})
            except InvalidTransitionError as e:
                return self._send(409, {"error": str(e)})
            except (ValidationError, ValueError) as e:
                return self._send(400, {"error": str(e)})

    return Handler


def serve(service: CareCoordinationService, port: int = 8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
    print(f"Care-coordination API listening on http://127.0.0.1:{port}")
    print("GET /health, POST /care-plans, GET /care-plans/{id}, POST /outbox/process")
    server.serve_forever()
