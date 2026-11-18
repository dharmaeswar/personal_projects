"""HTTP layer for the installment-loan backend service (stdlib only).

Endpoints:
  GET  /health                  -> {"status": "ok"}
  POST /v1/checkout             -> create a loan (Idempotency-Key header)
  GET  /v1/loans/{id}           -> loan summary
  GET  /v1/loans/{id}/schedule  -> amortization schedule
  POST /v1/loans/{id}/payments  -> apply a payment

Checkout writes through to the (simulated) ledger with retry + backoff.
Structured JSON logs go to stdout: one line per request with method, path,
status and latency.
"""

from __future__ import annotations

import itertools
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .idempotency import IdempotencyStore, SimulatedLedger, retry_with_backoff
from .models import Loan, ValidationError, build_schedule, validate_checkout

logger = logging.getLogger("payments_api")
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
)


class LoanStore:
    """Thread-safe in-memory loan store with sequential ids."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loans: dict[str, Loan] = {}
        self._counter = itertools.count(1)

    def create(self, cleaned: dict) -> Loan:
        with self._lock:
            loan_id = f"loan_{next(self._counter):06d}"
            loan = Loan(
                id=loan_id,
                schedule=build_schedule(
                    cleaned["principal_cents"],
                    cleaned["apr_bps"],
                    cleaned["term_months"],
                ),
                **cleaned,
            )
            self._loans[loan_id] = loan
            return loan

    def get(self, loan_id: str) -> Loan | None:
        with self._lock:
            return self._loans.get(loan_id)

    def count(self) -> int:
        with self._lock:
            return len(self._loans)


def make_handler(store: LoanStore, idempotency: IdempotencyStore, ledger: SimulatedLedger):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                parsed = json.loads(raw.decode())
            except (ValueError, UnicodeDecodeError):
                raise ValidationError("request body must be valid JSON")
            if not isinstance(parsed, dict):
                raise ValidationError("request body must be a JSON object")
            return parsed

        def _log(self, status: int, started: float) -> None:
            ms = round((time.time() - started) * 1000, 1)
            logger.info(
                json.dumps(
                    {
                        "method": self.command,
                        "path": urlparse(self.path).path,
                        "status": status,
                        "latency_ms": ms,
                    }
                )
            )

        def do_GET(self) -> None:
            started = time.time()
            path = urlparse(self.path).path
            if path == "/health":
                self._send(200, {"status": "ok"})
                self._log(200, started)
                return
            parts = [p for p in path.split("/") if p]
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "loans":
                loan = store.get(parts[2])
                if loan is None:
                    self._send(404, {"error": "loan not found"})
                    self._log(404, started)
                else:
                    self._send(200, loan.to_dict())
                    self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "loans" and parts[3] == "schedule":
                loan = store.get(parts[2])
                if loan is None:
                    self._send(404, {"error": "loan not found"})
                    self._log(404, started)
                else:
                    self._send(200, {"loan_id": loan.id, "schedule": loan.schedule})
                    self._log(200, started)
                return
            self._send(404, {"error": "not found"})
            self._log(404, started)

        def do_POST(self) -> None:
            started = time.time()
            path = urlparse(self.path).path
            try:
                if path == "/v1/checkout":
                    key = self.headers.get("Idempotency-Key")
                    if key:
                        cached = idempotency.get(key)
                        if cached is not None:
                            self._send(200, cached)
                            self._log(200, started)
                            return
                    cleaned = validate_checkout(self._read_json())
                    loan = store.create(cleaned)
                    retry_with_backoff(lambda: ledger.record_loan(loan.id))
                    response = loan.to_dict()
                    if key:
                        idempotency.put(key, response)
                    self._send(201, response)
                    self._log(201, started)
                    return
                parts = [p for p in path.split("/") if p]
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "loans" and parts[3] == "payments":
                    loan = store.get(parts[2])
                    if loan is None:
                        self._send(404, {"error": "loan not found"})
                        self._log(404, started)
                        return
                    body = self._read_json()
                    updated = loan.apply_payment(body.get("amount_cents"))
                    self._send(200, updated)
                    self._log(200, started)
                    return
                self._send(404, {"error": "not found"})
                self._log(404, started)
            except ValidationError as exc:
                self._send(400, {"error": str(exc)})
                self._log(400, started)

        def log_message(self, *args) -> None:
            pass

    return Handler


def create_server(port: int = 0, ledger_fail_times: int = 0) -> ThreadingHTTPServer:
    store = LoanStore()
    idempotency = IdempotencyStore()
    ledger = SimulatedLedger(fail_times=ledger_fail_times)
    handler = make_handler(store, idempotency, ledger)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.loan_store = store  # type: ignore[attr-defined]
    server.idempotency_store = idempotency  # type: ignore[attr-defined]
    server.ledger = ledger  # type: ignore[attr-defined]
    return server


def run(port: int = 8000) -> None:
    server = create_server(port)
    print(f"payments-api listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
