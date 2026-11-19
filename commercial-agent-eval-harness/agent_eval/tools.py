"""MCP-style tool server: the business systems agents call.

Every tool has a name, a short description, a JSON input schema and a
handler. The server validates arguments against the schema, dispatches the
call, and records a trace entry (tool, arguments, latency, cost, outcome)
through the supplied tracer. All data is synthetic and lives in memory.
"""

from __future__ import annotations

import copy

from .tracer import Tracer


class ToolError(Exception):
    """Raised when a tool call is invalid or the tool itself fails."""


# ---------------------------------------------------------------------------
# Synthetic business data. Nothing here is real: vendors, invoices, tickets
# and knowledge-base articles are invented for the evaluation harness.
# ---------------------------------------------------------------------------

INVOICES = {
    "INV-1001": {"invoice_id": "INV-1001", "vendor": "Acme Supplies",
                 "amount": 1250.00, "currency": "USD", "po_id": "PO-5001",
                 "status": "received"},
    "INV-1002": {"invoice_id": "INV-1002", "vendor": "Acme Supplies",
                 "amount": 980.00, "currency": "USD", "po_id": "PO-5002",
                 "status": "received"},
    "INV-1003": {"invoice_id": "INV-1003", "vendor": "Northwind Paper",
                 "amount": 4320.50, "currency": "USD", "po_id": "PO-5003",
                 "status": "received"},
    "INV-1004": {"invoice_id": "INV-1004", "vendor": "Unknown Vendor LLC",
                 "amount": 750.00, "currency": "USD", "po_id": "PO-9999",
                 "status": "received"},
    "INV-1005": {"invoice_id": "INV-1005", "vendor": "Acme Supplies",
                 "amount": 1250.00, "currency": "USD", "po_id": "PO-5001",
                 "status": "received"},
}

PURCHASE_ORDERS = {
    "PO-5001": {"po_id": "PO-5001", "vendor": "Acme Supplies",
                "amount": 1250.00, "status": "approved"},
    "PO-5002": {"po_id": "PO-5002", "vendor": "Acme Supplies",
                "amount": 875.00, "status": "approved"},
    "PO-5003": {"po_id": "PO-5003", "vendor": "Northwind Paper",
                "amount": 4320.50, "status": "approved"},
}

CUSTOMERS = {
    "CUST-01": {"customer_id": "CUST-01", "name": "Beta Retail Co",
                "plan": "business", "region": "US-East"},
    "CUST-02": {"customer_id": "CUST-02", "name": "Gamma Health Inc",
                "plan": "enterprise", "region": "US-West"},
}

TICKETS = {
    "TKT-2001": {"ticket_id": "TKT-2001", "customer_id": "CUST-01",
                 "subject": "How do I reset the password for my team?",
                 "body": "Our admin left and nobody can sign in to the dashboard.",
                 "category": None, "status": "open"},
    "TKT-2002": {"ticket_id": "TKT-2002", "customer_id": "CUST-02",
                 "subject": "Checkout API returns 500 errors since this morning",
                 "body": "All payment calls fail with a 500 error after the deploy.",
                 "category": None, "status": "open"},
    "TKT-2003": {"ticket_id": "TKT-2003", "customer_id": "CUST-01",
                 "subject": "Refund for duplicate charge on invoice INV-1001",
                 "body": "We were charged twice for the same order and need a refund.",
                 "category": None, "status": "open"},
    "TKT-2004": {"ticket_id": "TKT-2004", "customer_id": "CUST-02",
                 "subject": "How do I export last month's usage report?",
                 "body": "Need a CSV export of usage for finance review.",
                 "category": None, "status": "open"},
}

KB_ARTICLES = [
    {"article_id": "KB-01", "title": "Reset a team password",
     "keywords": ["password", "reset", "sign in", "login"],
     "body": "An admin can reset passwords from Settings > Team > Reset password."},
    {"article_id": "KB-02", "title": "Export a usage report as CSV",
     "keywords": ["export", "usage report", "csv", "download"],
     "body": "Go to Reports > Usage, pick the month, then Export CSV."},
    {"article_id": "KB-03", "title": "Refund policy for duplicate charges",
     "keywords": ["refund", "duplicate charge", "charged twice"],
     "body": "Duplicate charges are refunded after finance confirms the payment."},
]


def _validate(args, schema):
    """Minimal JSON-schema-style check: required keys and string/number types."""
    for key in schema.get("required", []):
        if key not in args:
            raise ToolError(f"missing required argument: {key}")
    for key, value in args.items():
        expected = schema.get("properties", {}).get(key, {}).get("type")
        if expected == "string" and not isinstance(value, str):
            raise ToolError(f"argument {key} must be a string")
        if expected == "number" and not isinstance(value, (int, float)):
            raise ToolError(f"argument {key} must be a number")
    for key in args:
        if key not in schema.get("properties", {}):
            raise ToolError(f"unknown argument: {key}")


class ToolServer:
    """Registry + dispatcher for the simulated business-system tools."""

    def __init__(self, tracer=None):
        self.tracer = tracer or Tracer()
        self._invoices = copy.deepcopy(INVOICES)
        self._pos = copy.deepcopy(PURCHASE_ORDERS)
        self._tickets = copy.deepcopy(TICKETS)
        self._approvals = []
        self._flags = []
        self._escalations = []
        self._resolutions = []
        self.tools = {
            "lookup_invoice": {
                "description": "Fetch an invoice by id.",
                "input_schema": {"type": "object",
                                 "properties": {"invoice_id": {"type": "string"}},
                                 "required": ["invoice_id"]},
                "handler": self._lookup_invoice,
            },
            "lookup_po": {
                "description": "Fetch a purchase order by id.",
                "input_schema": {"type": "object",
                                 "properties": {"po_id": {"type": "string"}},
                                 "required": ["po_id"]},
                "handler": self._lookup_po,
            },
            "approve_invoice": {
                "description": "Approve an invoice that matches its PO.",
                "input_schema": {"type": "object",
                                 "properties": {"invoice_id": {"type": "string"},
                                                "approver": {"type": "string"}},
                                 "required": ["invoice_id", "approver"]},
                "handler": self._approve_invoice,
            },
            "flag_invoice": {
                "description": "Flag an invoice for manual review with a reason.",
                "input_schema": {"type": "object",
                                 "properties": {"invoice_id": {"type": "string"},
                                                "reason": {"type": "string"}},
                                 "required": ["invoice_id", "reason"]},
                "handler": self._flag_invoice,
            },
            "lookup_customer": {
                "description": "Fetch a customer record by id.",
                "input_schema": {"type": "object",
                                 "properties": {"customer_id": {"type": "string"}},
                                 "required": ["customer_id"]},
                "handler": self._lookup_customer,
            },
            "get_ticket": {
                "description": "Fetch a support ticket by id.",
                "input_schema": {"type": "object",
                                 "properties": {"ticket_id": {"type": "string"}},
                                 "required": ["ticket_id"]},
                "handler": self._get_ticket,
            },
            "search_kb": {
                "description": "Search the knowledge base for an article.",
                "input_schema": {"type": "object",
                                 "properties": {"query": {"type": "string"}},
                                 "required": ["query"]},
                "handler": self._search_kb,
            },
            "resolve_ticket": {
                "description": "Resolve a ticket with a resolution note.",
                "input_schema": {"type": "object",
                                 "properties": {"ticket_id": {"type": "string"},
                                                "resolution": {"type": "string"}},
                                 "required": ["ticket_id", "resolution"]},
                "handler": self._resolve_ticket,
            },
            "escalate_ticket": {
                "description": "Escalate a ticket to a specialist team.",
                "input_schema": {"type": "object",
                                 "properties": {"ticket_id": {"type": "string"},
                                                "team": {"type": "string"},
                                                "reason": {"type": "string"}},
                                 "required": ["ticket_id", "team", "reason"]},
                "handler": self._escalate_ticket,
            },
        }

    # -- public API ---------------------------------------------------------
    def list_tools(self):
        return [{"name": name,
                 "description": spec["description"],
                 "input_schema": spec["input_schema"]}
                for name, spec in self.tools.items()]

    def call(self, name, args):
        """Validate, dispatch, and trace one tool call. Returns the result."""
        spec = self.tools.get(name)
        if spec is None:
            raise ToolError(f"unknown tool: {name}")
        try:
            _validate(args, spec["input_schema"])
            result = spec["handler"](args)
            self.tracer.record(name, args, "ok")
            return result
        except ToolError as exc:
            self.tracer.record(name, args, "error", error=str(exc))
            raise

    # -- handlers -----------------------------------------------------------
    def _lookup_invoice(self, args):
        inv = self._invoices.get(args["invoice_id"])
        if inv is None:
            raise ToolError(f"invoice not found: {args['invoice_id']}")
        return copy.deepcopy(inv)

    def _lookup_po(self, args):
        po = self._pos.get(args["po_id"])
        if po is None:
            raise ToolError(f"purchase order not found: {args['po_id']}")
        return copy.deepcopy(po)

    def _approve_invoice(self, args):
        inv = self._invoices.get(args["invoice_id"])
        if inv is None:
            raise ToolError(f"invoice not found: {args['invoice_id']}")
        if inv["status"] != "received":
            raise ToolError(f"invoice {args['invoice_id']} is {inv['status']}, cannot approve")
        inv["status"] = "approved"
        rec = {"invoice_id": inv["invoice_id"], "approver": args["approver"],
               "amount": inv["amount"]}
        self._approvals.append(rec)
        return copy.deepcopy(rec)

    def _flag_invoice(self, args):
        inv = self._invoices.get(args["invoice_id"])
        if inv is None:
            raise ToolError(f"invoice not found: {args['invoice_id']}")
        inv["status"] = "flagged"
        rec = {"invoice_id": inv["invoice_id"], "reason": args["reason"]}
        self._flags.append(rec)
        return copy.deepcopy(rec)

    def _lookup_customer(self, args):
        cust = CUSTOMERS.get(args["customer_id"])
        if cust is None:
            raise ToolError(f"customer not found: {args['customer_id']}")
        return copy.deepcopy(cust)

    def _get_ticket(self, args):
        tkt = self._tickets.get(args["ticket_id"])
        if tkt is None:
            raise ToolError(f"ticket not found: {args['ticket_id']}")
        return copy.deepcopy(tkt)

    def _search_kb(self, args):
        query = args["query"].lower()
        hits = [a for a in KB_ARTICLES
                if any(kw in query for kw in a["keywords"])]
        return [{"article_id": a["article_id"], "title": a["title"],
                 "body": a["body"]} for a in hits]

    def _resolve_ticket(self, args):
        tkt = self._tickets.get(args["ticket_id"])
        if tkt is None:
            raise ToolError(f"ticket not found: {args['ticket_id']}")
        tkt["status"] = "resolved"
        rec = {"ticket_id": tkt["ticket_id"], "resolution": args["resolution"]}
        self._resolutions.append(rec)
        return copy.deepcopy(rec)

    def _escalate_ticket(self, args):
        tkt = self._tickets.get(args["ticket_id"])
        if tkt is None:
            raise ToolError(f"ticket not found: {args['ticket_id']}")
        tkt["status"] = "escalated"
        rec = {"ticket_id": tkt["ticket_id"], "team": args["team"],
               "reason": args["reason"]}
        self._escalations.append(rec)
        return copy.deepcopy(rec)
