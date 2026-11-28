"""PostgreSQL / Amazon Aurora-style relational layer and query tuning.

Gold aggregates from the lakehouse are loaded into relational tables
with primary keys, foreign keys and indexes, the way an operational
PostgreSQL database or an Amazon Aurora MySQL cluster would hold them
for application queries. The local engine is SQLite (stdlib
``sqlite3``): it stands in for PostgreSQL/Aurora here because it runs
without a server, and the SQL used is standard SQL that runs on both.

What this module does, and where the stand-in ends:

- ``load_table`` writes a frame into a relational table with a
  declared primary key and foreign keys to already-loaded tables.
- ``postgres_ddl`` / ``aurora_mysql_ddl`` forward-engineer the same
  table as PostgreSQL or Aurora MySQL DDL text (types, keys, indexes)
  for review — the DDL is documentation, it is not executed locally.
- ``explain`` returns the query plan (``EXPLAIN QUERY PLAN``) so a
  full table scan is visible before tuning.
- ``tune_query`` creates the recommended index, re-runs the plan, and
  reports whether the scan became an index search — the performance
  loop the JD describes (query tuning, indexing, execution-plan
  analysis) on a small, checkable scale.

No PostgreSQL server, Aurora cluster or AWS account is involved, and
the README says so. Timings are reported but never asserted on: a
local SQLite timing is not a PostgreSQL benchmark.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# PostgreSQL / MySQL type mapping for the pandas dtypes this project uses.
_PG_TYPES = {
    "string": "TEXT",
    "int64": "BIGINT",
    "float64": "DOUBLE PRECISION",
    "datetime64[ns]": "TIMESTAMP",
    "bool": "BOOLEAN",
}
_MYSQL_TYPES = {
    "string": "VARCHAR(255)",
    "int64": "BIGINT",
    "float64": "DOUBLE",
    "datetime64[ns]": "DATETIME",
    "bool": "TINYINT(1)",
}


@dataclass
class ColumnDef:
    name: str
    dtype: str  # pandas dtype string, e.g. "string", "int64"
    nullable: bool = True


@dataclass
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str


@dataclass
class TableDef:
    name: str
    columns: list[ColumnDef] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    indexes: list[list[str]] = field(default_factory=list)

    def column(self, name: str) -> ColumnDef:
        for col in self.columns:
            if col.name == name:
                return col
        raise ValueError(f"table {self.name!r} has no column {name!r}")


def table_def_from_frame(
    name: str,
    df: pd.DataFrame,
    primary_key: list[str] | None = None,
    foreign_keys: list[ForeignKey] | None = None,
    indexes: list[list[str]] | None = None,
) -> TableDef:
    """Build a TableDef from a frame's dtypes (schema inferred, then fixed)."""
    columns = [
        ColumnDef(str(col), str(df[col].dtype), nullable=bool(df[col].isna().any()))
        for col in df.columns
    ]
    return TableDef(
        name=name,
        columns=columns,
        primary_key=primary_key or [],
        foreign_keys=foreign_keys or [],
        indexes=indexes or [],
    )


def postgres_ddl(table: TableDef) -> str:
    """Forward-engineer ``table`` as PostgreSQL DDL text."""
    lines = [f"CREATE TABLE {table.name} ("]
    defs = []
    for col in table.columns:
        pg_type = _PG_TYPES.get(col.dtype, "TEXT")
        null = "" if col.nullable else " NOT NULL"
        defs.append(f"    {col.name} {pg_type}{null}")
    if table.primary_key:
        defs.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
    for fk in table.foreign_keys:
        defs.append(
            f"    FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table} ({fk.ref_column})"
        )
    lines.append(",\n".join(defs))
    lines.append(");")
    for idx_cols in table.indexes:
        idx_name = f"idx_{table.name}_{'_'.join(idx_cols)}"
        lines.append(
            f"CREATE INDEX {idx_name} ON {table.name} ({', '.join(idx_cols)});"
        )
    return "\n".join(lines) + "\n"


def aurora_mysql_ddl(table: TableDef) -> str:
    """Forward-engineer ``table`` as Aurora MySQL DDL text."""
    lines = [f"CREATE TABLE {table.name} ("]
    defs = []
    for col in table.columns:
        my_type = _MYSQL_TYPES.get(col.dtype, "VARCHAR(255)")
        null = "" if col.nullable else " NOT NULL"
        defs.append(f"    {col.name} {my_type}{null}")
    if table.primary_key:
        defs.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
    for fk in table.foreign_keys:
        defs.append(
            f"    FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table} ({fk.ref_column})"
        )
    lines.append(",\n".join(defs))
    lines.append(") ENGINE=InnoDB;")
    for idx_cols in table.indexes:
        idx_name = f"idx_{table.name}_{'_'.join(idx_cols)}"
        lines.append(
            f"CREATE INDEX {idx_name} ON {table.name} ({', '.join(idx_cols)});"
        )
    return "\n".join(lines) + "\n"


class RelationalStore:
    """A relational store backed by local SQLite (stand-in for PostgreSQL/Aurora)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def load_table(self, table: TableDef, df: pd.DataFrame) -> int:
        """Create ``table`` (if needed) and load ``df`` into it. Returns rows loaded."""
        cols = ", ".join(
            f"{c.name} {'INTEGER' if c.dtype == 'int64' else 'REAL' if c.dtype == 'float64' else 'TEXT'}"
            for c in table.columns
        )
        pk = f", PRIMARY KEY ({', '.join(table.primary_key)})" if table.primary_key else ""
        fk = "".join(
            f", FOREIGN KEY ({f.column}) REFERENCES {f.ref_table} ({f.ref_column})"
            for f in table.foreign_keys
        )
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({cols}{pk}{fk})")
        placeholders = ", ".join("?" for _ in table.columns)
        col_names = ", ".join(c.name for c in table.columns)
        rows = []
        for _, row in df.iterrows():
            values = []
            for col in table.columns:
                value = row[col.name]
                if isinstance(value, pd.Timestamp):
                    value = value.isoformat()
                elif pd.isna(value):
                    value = None
                values.append(value)
            rows.append(tuple(values))
        self.conn.executemany(
            f"INSERT OR REPLACE INTO {table.name} ({col_names}) VALUES ({placeholders})",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def row_count(self, table_name: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    def explain(self, sql: str, params: tuple = ()) -> list[str]:
        """Return the query-plan lines for ``sql`` (EXPLAIN QUERY PLAN)."""
        cursor = self.conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
        return [f"{row[1]} {row[2]} {row[3]}".strip() for row in cursor.fetchall()]

    def time_query(self, sql: str, params: tuple = ()) -> tuple[list[tuple], float]:
        """Run ``sql`` and return (rows, seconds). Timing is informational only."""
        start = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        return rows, time.perf_counter() - start

    def create_index(self, table_name: str, columns: list[str]) -> str:
        """Create an index on ``columns``; returns its name."""
        name = f"idx_{table_name}_{'_'.join(columns)}"
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table_name} ({', '.join(columns)})"
        )
        self.conn.commit()
        return name


@dataclass
class TuningReport:
    """Before/after of one query-tuning step."""

    sql: str
    index_name: str
    plan_before: list[str]
    plan_after: list[str]
    seconds_before: float
    seconds_after: float
    rows: int

    @property
    def scanned_before(self) -> bool:
        # Any SCAN line is a full scan — including a scan that walks the
        # primary-key autoindex instead of the table itself.
        return any("SCAN" in line for line in self.plan_before)

    @property
    def uses_index_after(self) -> bool:
        # The plan must search with the index this tuning step added.
        return any(
            "SEARCH" in line and self.index_name in line for line in self.plan_after
        )


def tune_query(
    store: RelationalStore, sql: str, params: tuple, index_table: str, index_columns: list[str]
) -> TuningReport:
    """Tune ``sql``: plan it, add the index, plan it again, report the change.

    The verdict rests on the plan text (SCAN -> SEARCH USING INDEX),
    not on wall-clock time, so it is deterministic on small data.
    """
    plan_before = store.explain(sql, params)
    _, seconds_before = store.time_query(sql, params)
    index_name = store.create_index(index_table, index_columns)
    plan_after = store.explain(sql, params)
    rows, seconds_after = store.time_query(sql, params)
    return TuningReport(
        sql=sql,
        index_name=index_name,
        plan_before=plan_before,
        plan_after=plan_after,
        seconds_before=seconds_before,
        seconds_after=seconds_after,
        rows=len(rows),
    )


def render_tuning_report(report: TuningReport) -> str:
    lines = [
        f"Query: {report.sql}",
        f"Index added: {report.index_name}",
        "Plan before:",
        *[f"  {line}" for line in report.plan_before],
        "Plan after:",
        *[f"  {line}" for line in report.plan_after],
        f"Full scan before tuning: {report.scanned_before}",
        f"Index search after tuning: {report.uses_index_after}",
        f"Rows returned: {report.rows}",
        f"Seconds before: {report.seconds_before:.4f}; after: {report.seconds_after:.4f} (informational)",
    ]
    return "\n".join(lines) + "\n"
