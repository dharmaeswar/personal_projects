"""Expected schemas for every table, enforced before a write lands.

A schema is a mapping of column -> (python type, nullable). Rows are plain
dicts, so enforcement is explicit and dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SchemaProblem:
    table: str
    problem: str


CAMPAIGNS_SCHEMA: dict[str, tuple[type, bool]] = {
    "campaign_id": (str, False),
    "advertiser": (str, False),
    "channel": (str, False),
    "start_date": (str, False),
    "end_date": (str, False),
    "daily_budget_usd": (float, False),
}

ADS_SCHEMA: dict[str, tuple[type, bool]] = {
    "ad_id": (str, False),
    "campaign_id": (str, False),
    "format": (str, False),
    "placement": (str, False),
}

EVENTS_SCHEMA: dict[str, tuple[type, bool]] = {
    "event_id": (str, False),
    "ad_id": (str, False),
    "campaign_id": (str, True),  # nullable on purpose: bronze may carry nulls
    "event_ts": (str, False),
    "impressions": (int, False),
    "clicks": (int, False),
    "cpc_usd": (float, False),
    "spend_usd": (float, False),
}

GOLD_SCHEMA: dict[str, tuple[type, bool]] = {
    "event_date": (str, False),
    "campaign_id": (str, False),
    "channel": (str, False),
    "impressions": (int, False),
    "clicks": (int, False),
    "spend_usd": (float, False),
}

# Silver adds a late-arriving flag to the bronze event shape.
SILVER_SCHEMA: dict[str, tuple[type, bool]] = {
    **EVENTS_SCHEMA,
    "campaign_id": (str, False),
    "late_arriving": (int, False),
}


def enforce_schema(
    rows: list[dict], schema: dict[str, tuple[type, bool]], table: str
) -> list[SchemaProblem]:
    """Return every schema violation in ``rows`` (empty list = clean)."""
    problems: list[SchemaProblem] = []
    expected = set(schema)
    for i, row in enumerate(rows):
        keys = set(row)
        for missing in sorted(expected - keys):
            problems.append(
                SchemaProblem(table, f"row {i}: missing column: {missing}")
            )
        for extra in sorted(keys - expected):
            problems.append(
                SchemaProblem(table, f"row {i}: unexpected column: {extra}")
            )
        for col, (typ, nullable) in schema.items():
            if col not in row:
                continue
            value = row[col]
            if value is None:
                if not nullable:
                    problems.append(
                        SchemaProblem(
                            table,
                            f"row {i}: nulls in non-nullable column {col}",
                        )
                    )
                continue
            # bool is a subclass of int; exclude it from int columns.
            if isinstance(value, bool) or not isinstance(value, typ):
                # ints are acceptable where a float is expected.
                if typ is float and isinstance(value, int) and not isinstance(
                    value, bool
                ):
                    continue
                problems.append(
                    SchemaProblem(
                        table,
                        f"row {i}: column {col} has type "
                        f"{type(value).__name__}, expected {typ.__name__}",
                    )
                )
    return problems
