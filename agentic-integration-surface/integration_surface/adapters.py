"""Modernization capability adapters.

The adapters sit behind the tool surface: they turn a validated, authorized
tool call into work against a legacy modernization capability. The capabilities
here are small, deterministic models of AMP's real ones — schema analysis,
relational-to-document transformation, migration dry-run, and migrated-data
validation — run over synthetic sample schemas, so the integration layer can
be exercised end to end without any real database or model.

The "model" an agent would call is a seeded stub: given the same seed it
returns the same suggestion, so tests for nondeterministic model behaviour
can assert retry, timeout, and guardrail behaviour reproducibly.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .context import CallerContext
from .contracts import ContractError, PartialSuccess, ToolError, ToolResult


# ---------------------------------------------------------------------------
# Synthetic sample data: a small legacy relational schema, seeded in code.
# ---------------------------------------------------------------------------

SAMPLE_SCHEMAS: dict[str, dict] = {
    "orders": {
        "tables": {
            "customers": ["id", "name", "email", "created_at"],
            "orders": ["id", "customer_id", "total", "placed_at", "status"],
            "order_items": ["id", "order_id", "sku", "qty", "price"],
        },
        "foreign_keys": [("orders", "customer_id", "customers", "id"),
                         ("order_items", "order_id", "orders", "id")],
    },
    "billing": {
        "tables": {
            "accounts": ["id", "owner", "plan", "opened_at"],
            "invoices": ["id", "account_id", "amount", "due_at", "paid"],
            "payments": ["id", "invoice_id", "amount", "method", "received_at"],
        },
        "foreign_keys": [("invoices", "account_id", "accounts", "id"),
                         ("payments", "invoice_id", "invoices", "id")],
    },
}

# Relational type hints for the transformer, per column name pattern.
_TYPE_MAP = {
    "id": "ObjectId", "created_at": "Date", "placed_at": "Date",
    "due_at": "Date", "opened_at": "Date", "received_at": "Date",
    "total": "Decimal128", "amount": "Decimal128", "price": "Decimal128",
    "qty": "Int32", "paid": "Boolean",
}


@dataclass
class ModelStub:
    """Deterministic stand-in for a model call.

    ``suggest`` returns a transformation suggestion whose content depends on
    the seed, so the same seed always gives the same answer. ``flaky`` mode
    fails the first ``fail_times`` calls, letting tests exercise retry logic
    for nondeterministic model behaviour without a real model.
    """

    seed: int = 0
    fail_times: int = 0
    calls: int = 0

    def suggest(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ToolError("model_unavailable", "model call failed; retryable")
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest()
        choice = int(digest[:2], 16) % 3
        suggestions = [
            "embed child rows as an array in the parent document",
            "keep a reference and denormalize the display fields",
            "split into two collections with a lookup at read time",
        ]
        return suggestions[choice]


def _tenant_check(ctx: CallerContext, resource_tenant: str) -> None:
    if ctx.tenant_id != resource_tenant:
        raise ToolError(
            "forbidden",
            f"tenant {ctx.tenant_id} may not access resources of {resource_tenant}",
        )


# ---------------------------------------------------------------------------
# Handlers: one per tool. Each takes (ctx, args) and returns a ToolResult.
# ---------------------------------------------------------------------------

def analyze_schema(ctx: CallerContext, args: dict) -> ToolResult:
    """Summarize a legacy schema: tables, columns, join depth, embed candidates."""
    schema_name = args["schema"]
    schema = SAMPLE_SCHEMAS.get(schema_name)
    if schema is None:
        raise ToolError("not_found", f"unknown schema: {schema_name}")
    _tenant_check(ctx, args.get("tenant", ctx.tenant_id))
    tables = schema["tables"]
    join_depth = len(schema["foreign_keys"])
    embed_candidates = [
        child for (child, _, parent, _) in schema["foreign_keys"]
        if len(tables[child]) <= 5
    ]
    return ToolResult(
        ok=True,
        data={
            "schema": schema_name,
            "tables": len(tables),
            "columns": sum(len(c) for c in tables.values()),
            "join_depth": join_depth,
            "embed_candidates": embed_candidates,
            "recommendation": "embed small child tables; reference large ones",
        },
    )


def transform_table(ctx: CallerContext, args: dict) -> ToolResult:
    """Map one relational table to a MongoDB-style document shape."""
    schema = SAMPLE_SCHEMAS.get(args["schema"])
    if schema is None:
        raise ToolError("not_found", f"unknown schema: {args['schema']}")
    table = args["table"]
    if table not in schema["tables"]:
        raise ToolError("not_found", f"table {table} not in schema {args['schema']}")
    _tenant_check(ctx, args.get("tenant", ctx.tenant_id))
    fields = {
        col: _TYPE_MAP.get(col, "String") for col in schema["tables"][table]
    }
    children = [c for (c, fk, p, _) in schema["foreign_keys"] if p == table]
    strategy = args.get("strategy", "auto")
    if strategy == "auto":
        strategy = "embed" if children and len(schema["tables"][table]) <= 5 else "reference"
    return ToolResult(
        ok=True,
        data={
            "collection": table,
            "fields": fields,
            "child_tables": children,
            "strategy": strategy,
            "note": "primary key maps to _id; foreign keys become references or embedded arrays",
        },
    )


def transform_batch(ctx: CallerContext, args: dict) -> ToolResult:
    """Transform several tables at once; failures are reported per item."""
    partial = PartialSuccess()
    for table in args["tables"]:
        try:
            result = transform_table(ctx, {"schema": args["schema"], "table": table})
            partial.record(table, True, result.data)
        except ToolError as exc:
            partial.record(table, False, error=f"{exc.code}: {exc.message}")
    return partial.as_result(data={"schema": args["schema"]})


def dry_run_migration(ctx: CallerContext, args: dict) -> ToolResult:
    """Simulate a migration: validate the plan, then report per-table outcomes."""
    schema = SAMPLE_SCHEMAS.get(args["schema"])
    if schema is None:
        raise ToolError("not_found", f"unknown schema: {args['schema']}")
    _tenant_check(ctx, args.get("tenant", ctx.tenant_id))
    if args.get("mode") == "full" and args.get("allow_downtime") is False:
        raise ContractError("full migration requires allow_downtime=true")
    partial = PartialSuccess()
    for table in schema["tables"]:
        # Deterministic outcome: tables with an even-length name migrate cleanly.
        if len(table) % 2 == 0:
            partial.record(table, True, {"rows": 1000 + len(table) * 37, "warnings": []})
        else:
            partial.record(
                table, False,
                error="validation: unmapped column type in 2 columns; fix mapping and retry",
            )
    return partial.as_result(data={"schema": args["schema"], "mode": args.get("mode", "dry_run")})


def validate_migrated(ctx: CallerContext, args: dict) -> ToolResult:
    """Check migrated documents against the source: counts, keys, and samples."""
    if args["source_rows"] < 0 or args["migrated_rows"] < 0:
        raise ContractError("row counts cannot be negative")
    _tenant_check(ctx, args.get("tenant", ctx.tenant_id))
    missing = args["source_rows"] - args["migrated_rows"]
    checks = {
        "row_count_match": missing == 0,
        "primary_keys_unique": args.get("duplicate_keys", 0) == 0,
        "sample_values_match": args.get("sample_mismatches", 0) == 0,
    }
    return ToolResult(
        ok=all(checks.values()),
        data={"checks": checks, "missing_rows": missing},
        error=None if all(checks.values()) else ToolError(
            "validation_failed",
            f"migration validation failed: {missing} rows missing, "
            f"{args.get('duplicate_keys', 0)} duplicate keys, "
            f"{args.get('sample_mismatches', 0)} sample mismatches",
        ),
    )


def suggest_mapping(ctx: CallerContext, args: dict, model: ModelStub | None = None) -> ToolResult:
    """Ask the (stub) model for a mapping suggestion, with bounded retries.

    Nondeterministic model behaviour is handled explicitly: a failed model
    call is retried up to ``max_retries`` times, then reported as a retryable
    error with the attempt count — never silently retried forever, and never
    reported as a success.
    """
    model = model or ModelStub(seed=args.get("seed", 0))
    attempts = 0
    last_error: ToolError | None = None
    for attempts in range(1, args.get("max_retries", 2) + 2):
        try:
            suggestion = model.suggest(args["prompt"])
            return ToolResult(
                ok=True,
                data={"suggestion": suggestion, "attempts": attempts, "seed": args.get("seed", 0)},
            )
        except ToolError as exc:
            last_error = exc
    return ToolResult(
        ok=False,
        error=ToolError(
            "model_unavailable",
            f"model call failed after {attempts} attempts; retryable",
            details={"attempts": attempts},
        ),
    )


# ---------------------------------------------------------------------------
# Tool definitions (the surface an agent discovers).
# ---------------------------------------------------------------------------

def build_registry(model: ModelStub | None = None) -> "ToolRegistry":
    from .tools import Tool, ToolRegistry

    registry = ToolRegistry()
    registry.register(Tool(
        name="amp.analyze_schema", version="1.0",
        description="Summarize a legacy relational schema: tables, join depth, embed candidates.",
        input_schema={"type": "object", "required": ["schema"],
                      "properties": {"schema": {"type": "string", "enum": list(SAMPLE_SCHEMAS)},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:read",),
        handler=analyze_schema,
    ))
    registry.register(Tool(
        name="amp.transform_table", version="1.0",
        description="Map one relational table to a MongoDB document shape.",
        input_schema={"type": "object", "required": ["schema", "table"],
                      "properties": {"schema": {"type": "string", "enum": list(SAMPLE_SCHEMAS)},
                                     "table": {"type": "string"},
                                     "strategy": {"type": "string", "enum": ["auto", "embed", "reference"]},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:read",),
        handler=transform_table,
    ))
    registry.register(Tool(
        name="amp.transform_table", version="2.0",
        description="Map one relational table to a MongoDB document shape (v2: adds strategy).",
        input_schema={"type": "object", "required": ["schema", "table"],
                      "properties": {"schema": {"type": "string", "enum": list(SAMPLE_SCHEMAS)},
                                     "table": {"type": "string"},
                                     "strategy": {"type": "string", "enum": ["auto", "embed", "reference"]},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:read",),
        handler=transform_table,
    ))
    registry.register(Tool(
        name="amp.transform_batch", version="1.0",
        description="Transform several tables at once; per-item success/failure is reported.",
        input_schema={"type": "object", "required": ["schema", "tables"],
                      "properties": {"schema": {"type": "string", "enum": list(SAMPLE_SCHEMAS)},
                                     "tables": {"type": "array", "minItems": 1},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:read",),
        handler=transform_batch,
    ))
    registry.register(Tool(
        name="amp.dry_run_migration", version="1.0",
        description="Simulate a migration plan and report per-table outcomes.",
        input_schema={"type": "object", "required": ["schema"],
                      "properties": {"schema": {"type": "string", "enum": list(SAMPLE_SCHEMAS)},
                                     "mode": {"type": "string", "enum": ["dry_run", "full"]},
                                     "allow_downtime": {"type": "boolean"},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:migrate",),
        handler=dry_run_migration,
    ))
    registry.register(Tool(
        name="amp.validate_migrated", version="1.0",
        description="Check migrated documents against the source: counts, keys, samples.",
        input_schema={"type": "object", "required": ["source_rows", "migrated_rows"],
                      "properties": {"source_rows": {"type": "integer", "minimum": 0},
                                     "migrated_rows": {"type": "integer", "minimum": 0},
                                     "duplicate_keys": {"type": "integer", "minimum": 0},
                                     "sample_mismatches": {"type": "integer", "minimum": 0},
                                     "tenant": {"type": "string"}}},
        required_scopes=("amp:read",),
        handler=validate_migrated,
    ))
    registry.register(Tool(
        name="amp.suggest_mapping", version="1.0",
        description="Ask the model for a table-mapping suggestion, with bounded retries.",
        input_schema={"type": "object", "required": ["prompt"],
                      "properties": {"prompt": {"type": "string"},
                                     "seed": {"type": "integer"},
                                     "max_retries": {"type": "integer", "minimum": 0, "maximum": 5}}},
        required_scopes=("amp:read",),
        handler=lambda ctx, args: suggest_mapping(ctx, args, model),
    ))
    return registry
