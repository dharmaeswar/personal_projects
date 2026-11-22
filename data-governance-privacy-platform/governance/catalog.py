"""Metadata catalog for the data-governance platform.

Local simulation: datasets are registered in memory with their owner team,
source system, columns, retention window and legal-hold flag. In a real
deployment this would be backed by a metadata store (e.g. a Snowflake
information-schema harvester); here it runs entirely in memory so the demo
works anywhere with system Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .classify import Sensitivity

SYSTEMS = ("Snowflake", "S3", "Postgres")


@dataclass
class Column:
    """One column of a registered dataset."""

    name: str
    dtype: str = "string"
    sensitivity: Optional[Sensitivity] = None  # filled in by the classifier
    classification_rule: Optional[str] = None  # rule that set the sensitivity
    description: str = ""


@dataclass
class Dataset:
    """A registered dataset: its metadata plus its (synthetic) rows.

    Rows are plain in-memory dicts keyed by column name. This is a local
    simulation — not a Snowflake table, S3 object, or Postgres relation.
    """

    name: str
    owner_team: str
    system: str
    retention_days: int
    legal_hold: bool = False
    columns: List[Column] = field(default_factory=list)
    rows: List[Dict[str, object]] = field(default_factory=list)

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(f"dataset {self.name!r} has no column {name!r}")

    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


class Catalog:
    """Registry of datasets, keyed by dataset name."""

    def __init__(self) -> None:
        self._datasets: Dict[str, Dataset] = {}

    def register(self, dataset: Dataset) -> None:
        if dataset.system not in SYSTEMS:
            raise ValueError(f"unknown system {dataset.system!r}; expected one of {SYSTEMS}")
        if dataset.name in self._datasets:
            raise ValueError(f"dataset {dataset.name!r} is already registered")
        self._datasets[dataset.name] = dataset

    def get(self, name: str) -> Dataset:
        return self._datasets[name]

    def names(self) -> List[str]:
        return sorted(self._datasets)

    def all(self) -> List[Dataset]:
        return [self._datasets[n] for n in self.names()]

    def datasets_under_hold(self) -> List[Dataset]:
        return [d for d in self.all() if d.legal_hold]

    def __len__(self) -> int:
        return len(self._datasets)
