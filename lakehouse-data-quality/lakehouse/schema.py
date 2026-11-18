"""Expected schemas and schema enforcement for lakehouse tables.

Each table has one expected schema: column name, pandas dtype kind, and
whether nulls are allowed. ``enforce_schema`` rejects a frame that is
missing a column, has an unexpected column, or holds nulls in a
non-nullable column, and reports every problem it finds instead of
failing on the first one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str  # pandas dtype string, e.g. "string", "int64", "float64", "datetime64[ns]"
    nullable: bool = True


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnSpec] = field(default_factory=list)

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def nullable_columns(self) -> set[str]:
        return {c.name for c in self.columns if c.nullable}

    def non_nullable_columns(self) -> set[str]:
        return {c.name for c in self.columns if not c.nullable}


ORDERS_SCHEMA = TableSchema(
    "orders",
    [
        ColumnSpec("order_id", "string", nullable=False),
        ColumnSpec("customer_id", "string", nullable=False),
        ColumnSpec("product_id", "string", nullable=False),
        ColumnSpec("order_date", "datetime64[ns]", nullable=False),
        ColumnSpec("quantity", "int64", nullable=False),
        ColumnSpec("unit_price", "float64", nullable=False),
        ColumnSpec("total_amount", "float64", nullable=False),
        ColumnSpec("region", "string", nullable=False),
    ],
)

CUSTOMERS_SCHEMA = TableSchema(
    "customers",
    [
        ColumnSpec("customer_id", "string", nullable=False),
        ColumnSpec("customer_name", "string", nullable=False),
        ColumnSpec("region", "string", nullable=False),
        ColumnSpec("signup_date", "datetime64[ns]", nullable=False),
    ],
)

PRODUCTS_SCHEMA = TableSchema(
    "products",
    [
        ColumnSpec("product_id", "string", nullable=False),
        ColumnSpec("product_name", "string", nullable=False),
        ColumnSpec("category", "string", nullable=False),
        ColumnSpec("list_price", "float64", nullable=False),
    ],
)

GOLD_SCHEMA = TableSchema(
    "daily_revenue",
    [
        ColumnSpec("order_date", "datetime64[ns]", nullable=False),
        ColumnSpec("category", "string", nullable=False),
        ColumnSpec("region", "string", nullable=False),
        ColumnSpec("order_count", "int64", nullable=False),
        ColumnSpec("total_revenue", "float64", nullable=False),
    ],
)

SCHEMAS = {
    "orders": ORDERS_SCHEMA,
    "customers": CUSTOMERS_SCHEMA,
    "products": PRODUCTS_SCHEMA,
    "daily_revenue": GOLD_SCHEMA,
}


@dataclass
class SchemaViolation:
    table: str
    problem: str


def enforce_schema(df: pd.DataFrame, schema: TableSchema) -> list[SchemaViolation]:
    """Check ``df`` against ``schema``; return one violation per problem found."""
    violations: list[SchemaViolation] = []
    present = set(df.columns)
    for col in schema.columns:
        if col.name not in present:
            violations.append(
                SchemaViolation(schema.name, f"missing column: {col.name}")
            )
    for extra in sorted(present - set(schema.column_names())):
        violations.append(
            SchemaViolation(schema.name, f"unexpected column: {extra}")
        )
    for col in schema.columns:
        if col.name not in present:
            continue
        if not col.nullable and df[col.name].isna().any():
            n = int(df[col.name].isna().sum())
            violations.append(
                SchemaViolation(
                    schema.name, f"nulls in non-nullable column {col.name}: {n} rows"
                )
            )
    return violations


def cast_to_schema(df: pd.DataFrame, schema: TableSchema) -> pd.DataFrame:
    """Return ``df`` with each column cast to its schema dtype."""
    out = df.copy()
    for col in schema.columns:
        if col.name in out.columns:
            out[col.name] = out[col.name].astype(col.dtype)
    return out
