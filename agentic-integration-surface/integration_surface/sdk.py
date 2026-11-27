"""Client SDK: typed calls over the tool registry.

The SDK is the developer-facing surface: it wraps the registry so callers
invoke tools by name with typed arguments, and it always propagates the
caller's context (never a broader one). It is the same surface a CLI or an
agent framework would build on.
"""

from __future__ import annotations

from .adapters import ModelStub, build_registry
from .context import CallerContext
from .contracts import ToolResult
from .tools import ToolRegistry


class IntegrationClient:
    """Typed client for the AMP agentic integration surface."""

    def __init__(self, ctx: CallerContext, registry: ToolRegistry | None = None,
                 model: ModelStub | None = None):
        self.ctx = ctx
        self.registry = registry or build_registry(model)

    def list_tools(self) -> list[dict]:
        return self.registry.list_tools()

    def _call(self, name: str, args: dict, version: str = "1.0") -> ToolResult:
        return self.registry.invoke(name, args, self.ctx, version)

    def analyze_schema(self, schema: str) -> ToolResult:
        return self._call("amp.analyze_schema", {"schema": schema})

    def transform_table(self, schema: str, table: str,
                        strategy: str = "auto", version: str = "2.0") -> ToolResult:
        return self._call(
            "amp.transform_table",
            {"schema": schema, "table": table, "strategy": strategy},
            version,
        )

    def transform_batch(self, schema: str, tables: list[str]) -> ToolResult:
        return self._call("amp.transform_batch", {"schema": schema, "tables": tables})

    def dry_run_migration(self, schema: str, mode: str = "dry_run") -> ToolResult:
        return self._call(
            "amp.dry_run_migration",
            {"schema": schema, "mode": mode, "allow_downtime": mode == "full"},
        )

    def validate_migrated(self, source_rows: int, migrated_rows: int,
                          duplicate_keys: int = 0,
                          sample_mismatches: int = 0) -> ToolResult:
        return self._call("amp.validate_migrated", {
            "source_rows": source_rows, "migrated_rows": migrated_rows,
            "duplicate_keys": duplicate_keys, "sample_mismatches": sample_mismatches,
        })

    def suggest_mapping(self, prompt: str, seed: int = 0,
                        max_retries: int = 2) -> ToolResult:
        return self._call("amp.suggest_mapping", {
            "prompt": prompt, "seed": seed, "max_retries": max_retries,
        })
