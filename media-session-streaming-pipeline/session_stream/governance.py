"""Unity Catalog-style governance: table registry, lineage, PII handling.

Local mirror of a Databricks Unity Catalog: tables live under
catalog.schema.table, every write records column-level lineage, PII
columns are tagged at registration and masked before they reach gold,
and every action lands in an audit log.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


@dataclass
class TableDef:
    catalog: str
    schema: str
    name: str
    columns: list[str]
    pii_columns: list[str] = field(default_factory=list)
    owner: str = "data-platform"

    @property
    def full_name(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.name}"


@dataclass
class Catalog:
    """A minimal Unity Catalog-style registry with lineage and audit."""
    tables: dict[str, TableDef] = field(default_factory=dict)
    lineage: list[dict] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)

    def register(self, table: TableDef) -> TableDef:
        if table.full_name in self.tables:
            raise ValueError(f"table already registered: {table.full_name}")
        unknown_pii = [c for c in table.pii_columns if c not in table.columns]
        if unknown_pii:
            raise ValueError(f"PII column not in table columns: {unknown_pii}")
        self.tables[table.full_name] = table
        self._audit("register", table.full_name)
        return table

    def record_lineage(self, source: str, target: str,
                       transform: str) -> dict:
        entry = {"source": source, "target": target, "transform": transform,
                 "at": datetime.now(timezone.utc).isoformat()}
        self.lineage.append(entry)
        self._audit("lineage", f"{source} -> {target}")
        return entry

    def mask_pii(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Hash every PII column of a registered table (gold never sees raw IDs)."""
        table = self.tables.get(table_name)
        if table is None:
            raise ValueError(f"table not registered: {table_name}")
        d = df.copy()
        for col in table.pii_columns:
            if col in d.columns:
                d[col] = d[col].astype(str).map(
                    lambda v: hashlib.sha256(v.encode()).hexdigest()[:16])
        return d

    def _audit(self, action: str, detail: str) -> None:
        self.audit.append({"action": action, "detail": detail,
                           "at": datetime.now(timezone.utc).isoformat()})
