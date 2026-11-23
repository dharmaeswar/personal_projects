"""HTTP layer for the installment-loan backend service (stdlib only).

Endpoints:
  GET  /health                  -> {"status": "ok"}
  POST /v1/checkout             -> create a loan (Idempotency-Key header)
  GET  /v1/loans/{id}           -> loan summary
  GET  /v1/loans/{id}/schedule  -> amortization schedule
  POST /v1/loans/{id}/payments  -> apply a payment
  POST /v1/comms/messages       -> send a templated message (Idempotency-Key header)
  GET  /v1/comms/messages/{id}  -> message delivery record
  GET  /v1/comms/delivery       -> delivery monitoring summary
  GET/POST /v1/comms/preferences/{user_id} -> channel preferences + digest opt-in
  POST /v1/comms/digest         -> group messages into one digest
  POST /v1/policies             -> create an insurance policy
  GET  /v1/policies/{id}        -> policy summary
  GET  /v1/policies/{id}/quote  -> cached premium quote
  POST /v1/policies/{id}/claims -> file a claim on a policy
  GET  /v1/policies/{id}/claims -> claims filed on a policy
  POST /v1/claims/{id}/settle   -> approve or deny a claim
  GET  /v1/events               -> published domain events (optional ?topic=)
  POST /v1/products             -> create a retail product (unique sku)
  GET  /v1/products/{id}        -> product summary with on-hand stock
  POST /v1/products/{id}/restock -> add stock to a product
  GET  /v1/inventory/low-stock  -> products at or below the low-stock threshold
  POST /v1/orders               -> place an order (reserves stock atomically)
  GET  /v1/orders/{id}          -> order summary with totals
  POST /v1/orders/{id}/fulfill  -> mark a placed order fulfilled
  POST /v1/orders/{id}/cancel   -> cancel a placed order (stock returned)
  POST /v1/enterprise/instances -> register a self-hosted instance
  GET  /v1/enterprise/instances/{id} -> instance summary
  POST /v1/enterprise/instances/{id}/checks -> record a per-service health check
  GET  /v1/enterprise/instances/{id}/health -> aggregate instance health
  POST /v1/enterprise/instances/{id}/upgrades -> plan a rolling upgrade
  GET  /v1/enterprise/instances/{id}/diagnostics -> troubleshooting bundle
  GET  /v1/enterprise/alerts   -> active alerts across instances
  POST /v1/identity/events     -> ingest a batch of IAM/STS-style auth events
  GET  /v1/identity/events     -> raw events (?principal=&service=&outcome=&limit=)
  GET  /v1/identity/features/{principal} -> per-principal feature record for ML/LLM agents
  POST /v1/identity/query      -> filtered event query for ML models / LLM agents
  GET  /v1/identity/quality    -> data quality + freshness summary (raises stale alerts)
  GET  /v1/identity/alerts     -> active identity-pipeline alerts

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
from urllib.parse import parse_qs, urlparse

from .comms import (
    CHANNELS,
    CommsService,
    SimulatedProvider,
    TemplateError,
    UserPreferences,
    build_digest,
)
from .enterprise import (
    EnterpriseStore,
    validate_check,
    validate_instance,
    validate_upgrade,
)
from .identity import IdentityStore, validate_event, validate_query
from .idempotency import IdempotencyStore, SimulatedLedger, retry_with_backoff
from .insurance import (
    EventPublisher,
    PolicyStore,
    QuoteCache,
    compute_premium_cents,
    validate_policy,
)
from .models import Loan, ValidationError, build_schedule, validate_checkout
from .retail import RetailStore, validate_order, validate_product

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


def make_handler(
    store: LoanStore,
    idempotency: IdempotencyStore,
    ledger: SimulatedLedger,
    comms: CommsService,
    policy_store: PolicyStore,
    events: EventPublisher,
    quotes: QuoteCache,
    retail_store: RetailStore,
    enterprise_store: EnterpriseStore,
    identity_store: IdentityStore,
):
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
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "comms" and parts[2] == "delivery":
                self._send(200, comms.delivery_summary())
                self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "comms" and parts[2] == "messages":
                record = comms.get(parts[3])
                if record is None:
                    self._send(404, {"error": "message not found"})
                    self._log(404, started)
                else:
                    self._send(200, record)
                    self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "comms" and parts[2] == "preferences":
                user_id = parts[3]
                self._send(
                    200,
                    {
                        "user_id": user_id,
                        "channels": comms.preferences.channels_for(user_id),
                        "digest": comms.preferences.digest_enabled(user_id),
                    },
                )
                self._log(200, started)
                return
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
            if path == "/v1/events":
                topic = parse_qs(urlparse(self.path).query).get("topic", [None])[0]
                self._send(200, {"events": events.events(topic)})
                self._log(200, started)
                return
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "policies":
                policy = policy_store.get_policy(parts[2])
                if policy is None:
                    self._send(404, {"error": "policy not found"})
                    self._log(404, started)
                else:
                    self._send(200, policy.to_dict())
                    self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "policies" and parts[3] == "quote":
                policy = policy_store.get_policy(parts[2])
                if policy is None:
                    self._send(404, {"error": "policy not found"})
                    self._log(404, started)
                    return
                key = _quote_key(policy.to_dict())
                cached = quotes.get(key)
                if cached is None:
                    cached = policy.premium_cents
                    quotes.put(key, cached)
                    served_from_cache = False
                else:
                    served_from_cache = True
                self._send(
                    200,
                    {
                        "policy_id": policy.id,
                        "premium_cents": cached,
                        "cached": served_from_cache,
                    },
                )
                self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "policies" and parts[3] == "claims":
                policy = policy_store.get_policy(parts[2])
                if policy is None:
                    self._send(404, {"error": "policy not found"})
                    self._log(404, started)
                else:
                    claims = policy_store.claims_for_policy(policy.id)
                    self._send(
                        200,
                        {"policy_id": policy.id, "claims": [c.to_dict() for c in claims]},
                    )
                    self._log(200, started)
                return
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "products":
                product = retail_store.get_product(parts[2])
                if product is None:
                    self._send(404, {"error": "product not found"})
                    self._log(404, started)
                else:
                    self._send(200, product.to_dict())
                    self._log(200, started)
                return
            if path == "/v1/inventory/low-stock":
                self._send(
                    200,
                    {"products": [p.to_dict() for p in retail_store.low_stock()]},
                )
                self._log(200, started)
                return
            if len(parts) == 3 and parts[0] == "v1" and parts[1] == "orders":
                order = retail_store.get_order(parts[2])
                if order is None:
                    self._send(404, {"error": "order not found"})
                    self._log(404, started)
                else:
                    self._send(200, order.to_dict())
                    self._log(200, started)
                return
            if path == "/v1/enterprise/alerts":
                self._send(
                    200, {"alerts": enterprise_store.active_alerts()}
                )
                self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "enterprise" and parts[2] == "instances":
                instance = enterprise_store.get_instance(parts[3])
                if instance is None:
                    self._send(404, {"error": "instance not found"})
                    self._log(404, started)
                else:
                    self._send(200, instance.to_dict())
                    self._log(200, started)
                return
            if (
                len(parts) == 5
                and parts[0] == "v1"
                and parts[1] == "enterprise"
                and parts[2] == "instances"
                and parts[4] == "health"
            ):
                instance = enterprise_store.get_instance(parts[3])
                if instance is None:
                    self._send(404, {"error": "instance not found"})
                    self._log(404, started)
                else:
                    self._send(
                        200,
                        {
                            "instance_id": instance.id,
                            "health": instance.aggregate_health(),
                            "services": {
                                s: instance.latest_status(s)
                                for s in ("web", "git", "redis", "mysql", "queue", "search")
                            },
                        },
                    )
                    self._log(200, started)
                return
            if (
                len(parts) == 5
                and parts[0] == "v1"
                and parts[1] == "enterprise"
                and parts[2] == "instances"
                and parts[4] == "diagnostics"
            ):
                instance = enterprise_store.get_instance(parts[3])
                if instance is None:
                    self._send(404, {"error": "instance not found"})
                    self._log(404, started)
                else:
                    self._send(200, instance.diagnostics())
                    self._log(200, started)
                return
            if path == "/v1/identity/events":
                query = parse_qs(urlparse(self.path).query)
                filters = {}
                for field in ("principal", "service", "action", "outcome"):
                    value = query.get(field, [None])[0]
                    if value is not None:
                        filters[field] = value
                limit_raw = query.get("limit", [None])[0]
                try:
                    limit = int(limit_raw) if limit_raw is not None else None
                except ValueError:
                    self._send(400, {"error": "limit must be an integer"})
                    self._log(400, started)
                    return
                self._send(200, {"events": identity_store.events(filters, limit)})
                self._log(200, started)
                return
            if len(parts) == 4 and parts[0] == "v1" and parts[1] == "identity" and parts[2] == "features":
                record = identity_store.features(parts[3])
                if record is None:
                    self._send(404, {"error": "principal not found"})
                    self._log(404, started)
                else:
                    self._send(200, record)
                    self._log(200, started)
                return
            if path == "/v1/identity/quality":
                identity_store.check_freshness()
                self._send(200, identity_store.quality_summary())
                self._log(200, started)
                return
            if path == "/v1/identity/alerts":
                self._send(200, {"alerts": identity_store.active_alerts()})
                self._log(200, started)
                return
            self._send(404, {"error": "not found"})
            self._log(404, started)

        def do_POST(self) -> None:
            started = time.time()
            path = urlparse(self.path).path
            try:
                if path == "/v1/comms/messages":
                    body = self._read_json()
                    key = self.headers.get("Idempotency-Key") or body.get("idempotency_key")
                    record = comms.send(
                        template_name=body.get("template", ""),
                        user_id=body.get("user_id", ""),
                        recipient=body.get("recipient", ""),
                        variables=body.get("variables") or {},
                        channels=body.get("channels"),
                        idempotency_key=key,
                    )
                    self._send(201, record)
                    self._log(201, started)
                    return
                parts = [p for p in path.split("/") if p]
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "comms" and parts[2] == "preferences":
                    body = self._read_json()
                    channels = body.get("channels")
                    if channels is not None:
                        comms.preferences.set_channels(parts[3], channels)
                    if "digest" in body:
                        comms.preferences.set_digest(parts[3], body["digest"])
                    self._send(
                        200,
                        {
                            "user_id": parts[3],
                            "channels": comms.preferences.channels_for(parts[3]),
                            "digest": comms.preferences.digest_enabled(parts[3]),
                        },
                    )
                    self._log(200, started)
                    return
                if path == "/v1/comms/digest":
                    body = self._read_json()
                    rendered = [
                        {"subject": m.get("subject", ""), "body": m.get("body", "")}
                        for m in body.get("messages") or []
                    ]
                    digest = build_digest(
                        body.get("user_id", ""),
                        body.get("channel", "email"),
                        rendered,
                    )
                    self._send(200, digest)
                    self._log(200, started)
                    return
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
                if path == "/v1/policies":
                    cleaned = validate_policy(self._read_json())
                    key = _quote_key(cleaned)
                    cached = quotes.get(key)
                    if cached is None:
                        cached = compute_premium_cents(cleaned)
                        quotes.put(key, cached)
                    policy = policy_store.create_policy(cleaned)
                    events.publish(
                        "policy.created",
                        policy.id,
                        {"policy_id": policy.id, "premium_cents": policy.premium_cents},
                    )
                    self._send(201, policy.to_dict())
                    self._log(201, started)
                    return
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "policies" and parts[3] == "claims":
                    policy = policy_store.get_policy(parts[2])
                    if policy is None:
                        self._send(404, {"error": "policy not found"})
                        self._log(404, started)
                        return
                    body = self._read_json()
                    claim = policy_store.file_claim(
                        policy, body.get("amount_cents"), body.get("description", "")
                    )
                    events.publish(
                        "claim.filed",
                        claim.id,
                        {
                            "claim_id": claim.id,
                            "policy_id": policy.id,
                            "amount_cents": claim.amount_cents,
                        },
                    )
                    self._send(201, claim.to_dict())
                    self._log(201, started)
                    return
                if path == "/v1/products":
                    cleaned = validate_product(self._read_json())
                    product = retail_store.create_product(cleaned)
                    events.publish(
                        "product.created",
                        product.id,
                        {"product_id": product.id, "sku": product.sku},
                    )
                    self._send(201, product.to_dict())
                    self._log(201, started)
                    return
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "products" and parts[3] == "restock":
                    product = retail_store.get_product(parts[2])
                    if product is None:
                        self._send(404, {"error": "product not found"})
                        self._log(404, started)
                        return
                    body = self._read_json()
                    updated = retail_store.restock(product, body.get("quantity"))
                    self._send(200, updated.to_dict())
                    self._log(200, started)
                    return
                if path == "/v1/orders":
                    cleaned = validate_order(self._read_json())
                    order, low = retail_store.place_order(cleaned)
                    events.publish(
                        "order.placed",
                        order.id,
                        {
                            "order_id": order.id,
                            "customer_id": order.customer_id,
                            "total_cents": order.total_cents,
                        },
                    )
                    for product in low:
                        events.publish(
                            "inventory.low",
                            product.id,
                            {"product_id": product.id, "sku": product.sku, "stock": product.stock},
                        )
                    self._send(201, order.to_dict())
                    self._log(201, started)
                    return
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "orders" and parts[3] in ("fulfill", "cancel"):
                    order = retail_store.get_order(parts[2])
                    if order is None:
                        self._send(404, {"error": "order not found"})
                        self._log(404, started)
                        return
                    if parts[3] == "fulfill":
                        updated = retail_store.fulfill_order(order)
                        topic = "order.fulfilled"
                    else:
                        updated = retail_store.cancel_order(order)
                        topic = "order.cancelled"
                    events.publish(
                        topic,
                        updated.id,
                        {"order_id": updated.id, "status": updated.status},
                    )
                    self._send(200, updated.to_dict())
                    self._log(200, started)
                    return
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "claims" and parts[3] == "settle":
                    claim = policy_store.get_claim(parts[2])
                    if claim is None:
                        self._send(404, {"error": "claim not found"})
                        self._log(404, started)
                        return
                    body = self._read_json()
                    settled = policy_store.settle_claim(claim, body.get("decision", ""))
                    if settled.status == "settled":
                        events.publish(
                            "claim.settled",
                            settled.id,
                            {
                                "claim_id": settled.id,
                                "policy_id": settled.policy_id,
                                "payout_cents": settled.payout_cents,
                            },
                        )
                    self._send(200, settled.to_dict())
                    self._log(200, started)
                    return
                if path == "/v1/enterprise/instances":
                    cleaned = validate_instance(self._read_json())
                    instance = enterprise_store.create_instance(cleaned)
                    self._send(201, instance.to_dict())
                    self._log(201, started)
                    return
                if (
                    len(parts) == 5
                    and parts[0] == "v1"
                    and parts[1] == "enterprise"
                    and parts[2] == "instances"
                    and parts[4] == "checks"
                ):
                    instance = enterprise_store.get_instance(parts[3])
                    if instance is None:
                        self._send(404, {"error": "instance not found"})
                        self._log(404, started)
                        return
                    cleaned = validate_check(self._read_json())
                    recorded = instance.record_check(cleaned)
                    self._send(201, recorded)
                    self._log(201, started)
                    return
                if (
                    len(parts) == 5
                    and parts[0] == "v1"
                    and parts[1] == "enterprise"
                    and parts[2] == "instances"
                    and parts[4] == "upgrades"
                ):
                    instance = enterprise_store.get_instance(parts[3])
                    if instance is None:
                        self._send(404, {"error": "instance not found"})
                        self._log(404, started)
                        return
                    cleaned = validate_upgrade(self._read_json(), instance.version)
                    plan = instance.plan_upgrade(cleaned)
                    self._send(201, plan)
                    self._log(201, started)
                    return
                if path == "/v1/identity/events":
                    body = self._read_json()
                    summary = identity_store.ingest_batch(body.get("events"))
                    self._send(201, summary)
                    self._log(201, started)
                    return
                if path == "/v1/identity/query":
                    cleaned = validate_query(self._read_json())
                    self._send(
                        200,
                        identity_store.query(cleaned["filters"], cleaned["limit"]),
                    )
                    self._log(200, started)
                    return
                self._send(404, {"error": "not found"})
                self._log(404, started)
            except (ValidationError, TemplateError) as exc:
                self._send(400, {"error": str(exc)})
                self._log(400, started)

        def log_message(self, *args) -> None:
            pass

    return Handler


def _quote_key(fields: dict) -> str:
    """Deterministic cache key for a premium quote from policy fields."""
    return "|".join(
        str(fields[k])
        for k in (
            "policy_type",
            "coverage_limit_cents",
            "deductible_cents",
            "term_months",
            "state",
        )
    )


def create_server(
    port: int = 0, ledger_fail_times: int = 0, provider_fail_times: int = 0
) -> ThreadingHTTPServer:
    store = LoanStore()
    idempotency = IdempotencyStore()
    ledger = SimulatedLedger(fail_times=ledger_fail_times)
    comms = CommsService(SimulatedProvider(fail_times=provider_fail_times))
    policy_store = PolicyStore()
    events = EventPublisher()
    quotes = QuoteCache()
    retail_store = RetailStore()
    enterprise_store = EnterpriseStore()
    identity_store = IdentityStore()
    handler = make_handler(
        store, idempotency, ledger, comms, policy_store, events, quotes, retail_store,
        enterprise_store, identity_store,
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.loan_store = store  # type: ignore[attr-defined]
    server.idempotency_store = idempotency  # type: ignore[attr-defined]
    server.ledger = ledger  # type: ignore[attr-defined]
    server.comms_service = comms  # type: ignore[attr-defined]
    server.policy_store = policy_store  # type: ignore[attr-defined]
    server.events = events  # type: ignore[attr-defined]
    server.quotes = quotes  # type: ignore[attr-defined]
    server.retail_store = retail_store  # type: ignore[attr-defined]
    server.enterprise_store = enterprise_store  # type: ignore[attr-defined]
    server.identity_store = identity_store  # type: ignore[attr-defined]
    return server


def run(port: int = 8000) -> None:
    server = create_server(port)
    print(f"payments-api listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
