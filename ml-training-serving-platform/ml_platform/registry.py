"""Versioned model registry, persisted as JSON.

Stages: staging -> production -> archived. Only one version is production
at a time; promoting a version demotes the current production version to
archived and remembers it so a rollback can restore it.
"""

import json
import os
from datetime import datetime, timezone


class Registry:
    def __init__(self, path):
        self.path = path
        self._data = {"models": {}, "previous_production": None}
        if os.path.exists(path):
            with open(path) as f:
                self._data = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def register(self, name, model, metrics, version=None):
        """Register a trained model; returns its version string."""
        existing = [v for v in self._data["models"] if v.startswith(name + "-v")]
        version = version or f"{name}-v{len(existing) + 1}"
        if version in self._data["models"]:
            raise ValueError(f"version {version} already registered")
        self._data["models"][version] = {
            "name": name,
            "version": version,
            "stage": "staging",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "model": model.to_dict(),
        }
        self._save()
        return version

    def get(self, version):
        return self._data["models"].get(version)

    def production_version(self):
        for v, m in self._data["models"].items():
            if m["stage"] == "production":
                return v
        return None

    def promote(self, version):
        """Move a version to production; archive the old production one."""
        if version not in self._data["models"]:
            raise ValueError(f"unknown version {version}")
        current = self.production_version()
        if current == version:
            return version
        if current:
            self._data["models"][current]["stage"] = "archived"
            self._data["previous_production"] = current
        self._data["models"][version]["stage"] = "production"
        self._save()
        return version

    def rollback(self):
        """Restore the previous production version. Returns it, or None."""
        prev = self._data.get("previous_production")
        if not prev or prev not in self._data["models"]:
            return None
        current = self.production_version()
        if current:
            self._data["models"][current]["stage"] = "archived"
        self._data["models"][prev]["stage"] = "production"
        self._data["previous_production"] = current
        self._save()
        return prev

    def list_versions(self):
        return sorted(self._data["models"].values(), key=lambda m: m["created_at"])
