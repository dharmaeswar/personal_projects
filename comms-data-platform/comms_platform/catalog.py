"""Data catalog — a local model of the AWS Glue Data Catalog.

Datasets are registered with owner team, source system, schema, partitions
and retention. The catalog is what the serving layer and AI agents query
against: nothing is served unless it is registered here first.
"""

from __future__ import annotations

import json
from pathlib import Path


class Catalog:
    """A JSON-backed dataset registry (stands in for Glue Data Catalog)."""

    def __init__(self, path):
        self.path = Path(path)
        self._datasets = {}
        if self.path.exists():
            self._datasets = json.loads(self.path.read_text())

    def register(self, name, description, schema, partitions, location, owner):
        if name in self._datasets:
            raise ValueError(f"dataset {name} is already registered")
        self._datasets[name] = {
            "name": name,
            "description": description,
            "schema": schema,
            "partitions": partitions,
            "location": location,
            "owner": owner,
        }
        self._save()
        return self._datasets[name]

    def update(self, name, **fields):
        if name not in self._datasets:
            raise KeyError(f"dataset {name} is not registered")
        self._datasets[name].update(fields)
        self._save()
        return self._datasets[name]

    def describe(self, name):
        if name not in self._datasets:
            raise KeyError(f"dataset {name} is not registered")
        return dict(self._datasets[name])

    def search(self, keyword):
        keyword = keyword.lower()
        return [
            dict(d)
            for d in self._datasets.values()
            if keyword in d["name"].lower() or keyword in d["description"].lower()
        ]

    def list_names(self):
        return sorted(self._datasets)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._datasets, indent=2))
