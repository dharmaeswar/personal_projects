"""Rule-based configuration assistant.

A lightweight stand-in for an ML-backed assistant: it scores attribute
combinations against a small rule base learned from past configs and
suggests defaults for attributes left unset. It is deterministic and
explainable -- every suggestion names the rule that produced it -- so a
product team can audit it before accepting a suggestion.
"""

from __future__ import annotations

from .models import ProductConfig

# (module, attribute) -> default value, with the rule that justifies it.
DEFAULT_RULES: dict[tuple[str, str], tuple[object, str]] = {
    ("sizing", "size-run"): (["US 7", "US 8", "US 9", "US 10", "US 11"], "standard footwear size run"),
    ("materials", "upper-material"): ("engineered-mesh", "most common upper in past configs"),
    ("colourways", "primary-colour"): ("black", "most common primary colour in past configs"),
    ("pricing", "currency"): ("USD", "default currency for US product lines"),
}

# Attribute pairs that must not both be set to the listed values.
CONFLICT_RULES: list[tuple[str, str, object, str, str, object, str]] = [
    ("materials", "upper-material", "suede", "colourways", "primary-colour", "white",
     "suede in white stains easily; pick a darker colourway or a different upper"),
]


def suggest_defaults(config: ProductConfig) -> dict:
    """Return {module.attribute: {value, rule}} for unset attributes."""
    suggestions = {}
    known = {
        (m.name, a.name): a.value
        for m in config.modules
        for a in m.attributes
    }
    for (module, attr), (value, rule) in DEFAULT_RULES.items():
        if (module, attr) not in known:
            suggestions[f"{module}.{attr}"] = {"value": value, "rule": rule}
    return suggestions


def check_conflicts(config: ProductConfig) -> list[str]:
    """Return human-readable warnings for conflicting attribute pairs."""
    values = {
        (m.name, a.name): a.value
        for m in config.modules
        for a in m.attributes
    }
    warnings = []
    for mod_a, attr_a, val_a, mod_b, attr_b, val_b, message in CONFLICT_RULES:
        if values.get((mod_a, attr_a)) == val_a and values.get((mod_b, attr_b)) == val_b:
            warnings.append(message)
    return warnings


def completeness_score(config: ProductConfig) -> float:
    """Fraction of required attributes that have a non-empty value."""
    required = [
        a for m in config.modules for a in m.attributes if a.required
    ]
    if not required:
        return 1.0
    filled = sum(1 for a in required if a.value not in (None, "", []))
    return round(filled / len(required), 2)
