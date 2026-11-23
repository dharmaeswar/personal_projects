"""DynamoDB-style key-value store for product configs.

Partition key is product_id, sort key is version. The store is backed by
a single JSON file so the service runs locally with no AWS account; the
access pattern (get/put/query by partition key, latest-version lookup)
mirrors a DynamoDB table with a composite key.
"""

from __future__ import annotations

import json
import os

from .models import ProductConfig


class ConfigStore:
    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, dict[str, dict]] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for product_id, versions in raw.items():
                self._data[product_id] = {
                    str(v): cfg for v, cfg in versions.items()
                }

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def put(self, config: ProductConfig) -> ProductConfig:
        versions = self._data.setdefault(config.product_id, {})
        key = str(config.version)
        if key in versions:
            raise ValueError(
                f"version {config.version} of {config.product_id!r} already exists"
            )
        versions[key] = config.to_dict()
        self._save()
        return config

    def get(self, product_id: str, version: int) -> ProductConfig | None:
        versions = self._data.get(product_id)
        if not versions:
            return None
        raw = versions.get(str(version))
        return ProductConfig.from_dict(raw) if raw else None

    def latest(self, product_id: str) -> ProductConfig | None:
        versions = self._data.get(product_id)
        if not versions:
            return None
        top = max(int(v) for v in versions)
        return ProductConfig.from_dict(versions[str(top)])

    def latest_published(self, product_id: str) -> ProductConfig | None:
        versions = self._data.get(product_id)
        if not versions:
            return None
        published = [
            ProductConfig.from_dict(raw)
            for raw in versions.values()
            if raw.get("status") == "published"
        ]
        if not published:
            return None
        return max(published, key=lambda c: c.version)

    def list_products(self) -> list[str]:
        return sorted(self._data)

    def update(self, config: ProductConfig) -> ProductConfig:
        """Overwrite an existing version in place (status transitions)."""
        versions = self._data.get(config.product_id)
        if not versions or str(config.version) not in versions:
            raise KeyError(
                f"version {config.version} of {config.product_id!r} not found"
            )
        versions[str(config.version)] = config.to_dict()
        self._save()
        return config
