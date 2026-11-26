"""Tenant schema registry for the multi-tenant query platform.

Tenants define their own schemas (the Box Query Platform idea: customers
define schemas, then query their data in real time). A schema is versioned:
changing a schema creates a new version; documents are validated against the
version they were written with, and readers can ask for any version.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FIELD_TYPES = ("string", "number", "boolean", "string_list", "timestamp")


@dataclass(frozen=True)
class FieldDef:
    name: str
    type: str
    required: bool = False
    indexed: bool = True

    def __post_init__(self):
        if self.type not in FIELD_TYPES:
            raise ValueError(f"unknown field type {self.type!r}")
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError(f"bad field name {self.name!r}")


@dataclass
class SchemaVersion:
    tenant: str
    collection: str
    version: int
    fields: list[FieldDef]

    def field_map(self) -> dict[str, FieldDef]:
        return {f.name: f for f in self.fields}

    def validate(self, doc: dict) -> list[str]:
        """Return a list of validation errors; empty means the doc is valid."""
        errors = []
        fmap = self.field_map()
        for name, fdef in fmap.items():
            if fdef.required and name not in doc:
                errors.append(f"missing required field {name!r}")
        for name, value in doc.items():
            fdef = fmap.get(name)
            if fdef is None:
                errors.append(f"unknown field {name!r} for this schema version")
                continue
            if fdef.type == "string" and not isinstance(value, str):
                errors.append(f"field {name!r} must be a string")
            elif fdef.type == "number" and not isinstance(value, (int, float)):
                errors.append(f"field {name!r} must be a number")
            elif fdef.type == "boolean" and not isinstance(value, bool):
                errors.append(f"field {name!r} must be a boolean")
            elif fdef.type == "string_list" and (
                not isinstance(value, list) or not all(isinstance(v, str) for v in value)
            ):
                errors.append(f"field {name!r} must be a list of strings")
            elif fdef.type == "timestamp" and not isinstance(value, (int, float)):
                errors.append(f"field {name!r} must be a numeric timestamp")
        return errors


class SchemaRegistry:
    """Per-tenant, per-collection versioned schemas."""

    def __init__(self):
        self._schemas: dict[tuple[str, str], list[SchemaVersion]] = {}

    def register(self, tenant: str, collection: str, fields: list[FieldDef]) -> SchemaVersion:
        key = (tenant, collection)
        versions = self._schemas.setdefault(key, [])
        version = SchemaVersion(tenant, collection, len(versions) + 1, list(fields))
        versions.append(version)
        return version

    def latest(self, tenant: str, collection: str) -> SchemaVersion | None:
        versions = self._schemas.get((tenant, collection))
        return versions[-1] if versions else None

    def get(self, tenant: str, collection: str, version: int) -> SchemaVersion | None:
        for v in self._schemas.get((tenant, collection), []):
            if v.version == version:
                return v
        return None

    def collections(self, tenant: str) -> list[str]:
        return sorted({c for (t, c) in self._schemas if t == tenant})
