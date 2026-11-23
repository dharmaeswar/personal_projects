"""Service layer: validation, versioning, and the publish workflow.

The publish workflow mirrors an AWS Step Functions state machine:
draft -> review -> published, with a guard that a config must pass
validation before it can move to review, and only a reviewed config can
be published. Every publish creates a new immutable version, so a
consuming web app can pin the version it renders.
"""

from __future__ import annotations

from .ai_assist import suggest_defaults
from .models import ProductConfig
from .store import ConfigStore

# Step Functions-style state machine: allowed transitions.
TRANSITIONS = {
    "draft": ("review", "archived"),
    "review": ("published", "draft"),
    "published": ("archived",),
    "archived": (),
}


class ValidationError(ValueError):
    pass


class ConfigService:
    def __init__(self, store: ConfigStore):
        self.store = store

    def create(self, data: dict) -> ProductConfig:
        config = ProductConfig.from_dict(data)
        errors = config.validate()
        if errors:
            raise ValidationError("; ".join(errors))
        if self.store.get(config.product_id, config.version):
            raise ValidationError(
                f"version {config.version} of {config.product_id!r} already exists"
            )
        return self.store.put(config)

    def create_next_version(self, product_id: str, data: dict) -> ProductConfig:
        latest = self.store.latest(product_id)
        version = (latest.version + 1) if latest else 1
        data = dict(data, product_id=product_id, version=version, status="draft")
        return self.create(data)

    def get(self, product_id: str, version: int | None = None) -> ProductConfig:
        config = (
            self.store.get(product_id, version)
            if version is not None
            else self.store.latest(product_id)
        )
        if config is None:
            raise KeyError(f"product {product_id!r} not found")
        return config

    def get_published(self, product_id: str) -> ProductConfig:
        config = self.store.latest_published(product_id)
        if config is None:
            raise KeyError(f"no published config for {product_id!r}")
        return config

    def transition(self, product_id: str, version: int, target: str) -> ProductConfig:
        config = self.get(product_id, version)
        allowed = TRANSITIONS.get(config.status, ())
        if target not in allowed:
            raise ValidationError(
                f"cannot move {config.status!r} -> {target!r}; allowed: {list(allowed)}"
            )
        if target == "review":
            errors = config.validate()
            if errors:
                raise ValidationError("; ".join(errors))
        config.status = target
        return self.store.update(config)

    def publish(self, product_id: str, version: int) -> ProductConfig:
        """Run the full publish workflow: draft -> review -> published."""
        config = self.get(product_id, version)
        if config.status == "draft":
            config = self.transition(product_id, version, "review")
        if config.status == "review":
            config = self.transition(product_id, version, "published")
        if config.status != "published":
            raise ValidationError(f"config is {config.status!r}, cannot publish")
        return config

    def defaults_for(self, product_id: str, version: int) -> dict:
        """Attribute default suggestions for a config (see ai_assist)."""
        config = self.get(product_id, version)
        return suggest_defaults(config)
