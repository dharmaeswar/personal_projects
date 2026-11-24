"""Versioned data contracts for every pipeline table.

A contract is the shared agreement between the producers that write a
table and the consumers that read it: the exact columns, their types,
nullability, allowed value ranges, and the owner who signs off on a
change. Bumping a contract version is a deliberate, reviewed act — a
producer that ships a new column or a renamed field without bumping the
version is a contract violation, not a silent schema drift.

Contracts are checked in two places: at write time (``validate_contract``,
before silver or gold rows are accepted) and at read time by the
governance agent (``detect_drift``), which compares the rows actually
present against the contract on file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import EVENTS_SCHEMA, GOLD_SCHEMA, SILVER_SCHEMA


@dataclass
class ContractViolation:
    contract: str
    problem: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.contract}] {self.problem}"


@dataclass
class DataContract:
    """One versioned agreement for one table."""

    name: str
    version: int
    table: str
    owner: str
    fields: dict[str, tuple[type, bool]]
    ranges: dict[str, tuple[float | None, float | None]] = field(
        default_factory=dict
    )
    description: str = ""

    def columns(self) -> list[str]:
        return sorted(self.fields)


CONTRACTS: dict[str, DataContract] = {
    "events_bronze": DataContract(
        name="events_bronze",
        version=1,
        table="events_bronze",
        owner="dsp-analytics-ingest",
        fields=dict(EVENTS_SCHEMA),
        ranges={
            "impressions": (0, None),
            "clicks": (0, None),
            "spend_usd": (0, None),
            "cpc_usd": (0, None),
        },
        description="Raw ad events as delivered by the DSP event stream.",
    ),
    "events_silver": DataContract(
        name="events_silver",
        version=1,
        table="events_silver",
        owner="dsp-analytics-platform",
        fields=dict(SILVER_SCHEMA),
        ranges={
            "impressions": (0, None),
            "clicks": (0, None),
            "spend_usd": (0, None),
            "cpc_usd": (0, None),
        },
        description="Cleaned, deduplicated events; late arrivals flagged, not dropped.",
    ),
    "gold_daily_spend": DataContract(
        name="gold_daily_spend",
        version=1,
        table="gold_daily_spend",
        owner="dsp-analytics-platform",
        fields=dict(GOLD_SCHEMA),
        ranges={
            "impressions": (0, None),
            "clicks": (0, None),
            "spend_usd": (0, None),
        },
        description="Daily spend, impressions and clicks by campaign and channel.",
    ),
}


def validate_contract(
    rows: list[dict], contract: DataContract
) -> list[ContractViolation]:
    """Check rows against a contract; empty list means the contract holds."""
    violations: list[ContractViolation] = []
    expected = set(contract.fields)
    for i, row in enumerate(rows):
        keys = set(row)
        for missing in sorted(expected - keys):
            violations.append(
                ContractViolation(
                    contract.name, f"row {i}: missing column: {missing}"
                )
            )
        for extra in sorted(keys - expected):
            violations.append(
                ContractViolation(
                    contract.name, f"row {i}: unexpected column: {extra}"
                )
            )
        for col, (typ, nullable) in contract.fields.items():
            if col not in row:
                continue
            value = row[col]
            if value is None:
                if not nullable:
                    violations.append(
                        ContractViolation(
                            contract.name,
                            f"row {i}: nulls in non-nullable column {col}",
                        )
                    )
                continue
            if isinstance(value, bool) or not isinstance(value, typ):
                if typ is float and isinstance(value, int) and not isinstance(
                    value, bool
                ):
                    continue
                violations.append(
                    ContractViolation(
                        contract.name,
                        f"row {i}: column {col} has type "
                        f"{type(value).__name__}, expected {typ.__name__}",
                    )
                )
        for col, (low, high) in contract.ranges.items():
            value = row.get(col)
            if value is None or isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)):
                continue  # wrong-type violation already reported above
            if (low is not None and value < low) or (
                high is not None and value > high
            ):
                violations.append(
                    ContractViolation(
                        contract.name,
                        f"row {i}: {col}={value} outside [{low}, {high}]",
                    )
                )
    return violations


def detect_drift(
    rows: list[dict], contract: DataContract
) -> dict[str, list[str]]:
    """Compare the shape of ``rows`` with the contract on file.

    Returns added columns, removed columns, and columns whose observed
    Python type differs from the contract — the three drift signals a
    governance review cares about, without re-running every row check.
    """
    observed_types: dict[str, set[str]] = {}
    for row in rows:
        for col, value in row.items():
            if value is not None:
                observed_types.setdefault(col, set()).add(type(value).__name__)
    contract_cols = set(contract.fields)
    observed_cols = set(observed_types) | {
        col for row in rows for col in row if row[col] is None
    }
    type_changes = []
    for col in sorted(contract_cols & observed_cols):
        expected = contract.fields[col][0].__name__
        seen = observed_types.get(col, set())
        if seen and expected not in seen and not (
            expected == "float" and seen <= {"int", "float"}
        ):
            type_changes.append(
                f"{col}: contract {expected}, observed {sorted(seen)}"
            )
    return {
        "added_columns": sorted(observed_cols - contract_cols),
        "removed_columns": sorted(contract_cols - observed_cols),
        "type_changes": type_changes,
    }


def contract_summary(contract: DataContract) -> str:
    return (
        f"{contract.name} v{contract.version} (owner: {contract.owner}): "
        f"{len(contract.fields)} columns — {', '.join(contract.columns())}"
    )
