"""Domain models for product configuration.

A product configuration is a versioned, modular capability definition:
a product (e.g. a footwear line) has named modules (e.g. "materials",
"sizing", "colourways"), each module has attributes with typed values,
and the whole config moves through a lifecycle: draft -> review ->
published. Only published configs are served to consuming web apps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VALID_STATUSES = ("draft", "review", "published", "archived")
VALID_TYPES = ("string", "number", "boolean", "enum")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")


@dataclass
class Attribute:
    """One configurable attribute inside a module."""

    name: str
    type: str
    value: object
    options: list = field(default_factory=list)  # allowed values for enum
    required: bool = False

    def validate(self) -> list[str]:
        errors = []
        if not _ID_RE.match(self.name):
            errors.append(f"attribute name {self.name!r} must be lowercase slug")
        if self.type not in VALID_TYPES:
            errors.append(f"attribute {self.name!r}: unknown type {self.type!r}")
            return errors
        if self.type == "enum":
            if not self.options:
                errors.append(f"enum attribute {self.name!r} needs options")
            elif self.value not in self.options:
                errors.append(
                    f"enum attribute {self.name!r}: value {self.value!r} "
                    f"not in {self.options}"
                )
        if self.type == "number" and not isinstance(self.value, (int, float)):
            errors.append(f"number attribute {self.name!r} needs a numeric value")
        if self.type == "boolean" and not isinstance(self.value, bool):
            errors.append(f"boolean attribute {self.name!r} needs a boolean value")
        if self.type == "string" and not isinstance(self.value, str):
            errors.append(f"string attribute {self.name!r} needs a string value")
        return errors


@dataclass
class Module:
    """A named group of attributes, e.g. 'materials' or 'sizing'."""

    name: str
    attributes: list[Attribute] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors = []
        if not _ID_RE.match(self.name):
            errors.append(f"module name {self.name!r} must be lowercase slug")
        seen = set()
        for attr in self.attributes:
            if attr.name in seen:
                errors.append(f"duplicate attribute {attr.name!r} in module {self.name!r}")
            seen.add(attr.name)
            errors.extend(attr.validate())
        return errors


@dataclass
class ProductConfig:
    """A versioned product configuration."""

    product_id: str
    name: str
    version: int = 1
    status: str = "draft"
    modules: list[Module] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors = []
        if not _ID_RE.match(self.product_id):
            errors.append(f"product_id {self.product_id!r} must be lowercase slug")
        if not self.name.strip():
            errors.append("product name must not be empty")
        if self.version < 1:
            errors.append("version must be >= 1")
        if self.status not in VALID_STATUSES:
            errors.append(f"unknown status {self.status!r}")
        if not self.modules:
            errors.append("config needs at least one module")
        seen = set()
        for module in self.modules:
            if module.name in seen:
                errors.append(f"duplicate module {module.name!r}")
            seen.add(module.name)
            errors.extend(module.validate())
        return errors

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "modules": [
                {
                    "name": m.name,
                    "attributes": [
                        {
                            "name": a.name,
                            "type": a.type,
                            "value": a.value,
                            "options": a.options,
                            "required": a.required,
                        }
                        for a in m.attributes
                    ],
                }
                for m in self.modules
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProductConfig":
        modules = [
            Module(
                name=m["name"],
                attributes=[Attribute(**a) for a in m.get("attributes", [])],
            )
            for m in data.get("modules", [])
        ]
        return cls(
            product_id=data["product_id"],
            name=data["name"],
            version=data.get("version", 1),
            status=data.get("status", "draft"),
            modules=modules,
        )
