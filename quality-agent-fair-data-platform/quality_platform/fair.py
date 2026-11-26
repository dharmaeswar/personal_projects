"""FAIR data-product registry for Quality analytics.

A FAIR data product is Findable (searchable metadata), Accessible
(governed, role-based access), Interoperable (versioned standard schema)
and Reusable (documented interfaces, clear ownership). All products here
are registered over synthetic, seeded quality data — no real company data.
"""

from datetime import datetime, timedelta

REQUIRED_FIELDS = (
    "product_id", "name", "domain", "owner", "description",
    "schema", "freshness_sla_hours", "quality_score",
    "access_level", "version", "status",
)
ACCESS_LEVELS = ("public", "internal", "restricted")
STATUSES = ("live", "draft", "deprecated")
# Roles allowed to read a restricted product.
RESTRICTED_ROLES = ("quality-admin", "data-steward")


class RegistryError(ValueError):
    """Raised when a product registration or lookup is invalid."""


def validate_product(product):
    """Return a list of validation errors; empty list means valid."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in product or product[field] in (None, "", []):
            errors.append(f"missing required field: {field}")
    if errors:
        return errors
    if not isinstance(product["schema"], list) or not all(
        isinstance(f, dict) and "name" in f and "type" in f
        for f in product["schema"]
    ):
        errors.append("schema must be a list of {name, type} fields")
    if not (0 <= product["quality_score"] <= 100):
        errors.append("quality_score must be between 0 and 100")
    if product["access_level"] not in ACCESS_LEVELS:
        errors.append(f"access_level must be one of {ACCESS_LEVELS}")
    if product["status"] not in STATUSES:
        errors.append(f"status must be one of {STATUSES}")
    if product["freshness_sla_hours"] <= 0:
        errors.append("freshness_sla_hours must be positive")
    return errors


class FairRegistry:
    """In-memory registry of FAIR data products plus their lineage."""

    def __init__(self):
        self._products = {}
        self._lineage = {}

    def register(self, product, lineage=None):
        """Register a product. Raises RegistryError on invalid input."""
        errors = validate_product(product)
        if errors:
            raise RegistryError("; ".join(errors))
        pid = product["product_id"]
        if pid in self._products:
            raise RegistryError(f"duplicate product_id: {pid}")
        self._products[pid] = dict(product)
        self._lineage[pid] = list(lineage or [])
        return pid

    def get(self, product_id):
        """Return the product dict or None."""
        return self._products.get(product_id)

    def list_live(self):
        """All live products, sorted by product_id."""
        return [p for p in sorted(self._products.values(), key=lambda p: p["product_id"])
                if p["status"] == "live"]

    def search(self, query, domain=None, min_quality=None):
        """Ranked search over live products only.

        Name matches weigh double; description and keyword matches weigh
        one. Draft and deprecated products never surface.
        """
        terms = [t.lower() for t in query.split() if t]
        scored = []
        for product in self.list_live():
            if domain and product["domain"] != domain:
                continue
            if min_quality is not None and product["quality_score"] < min_quality:
                continue
            name = product["name"].lower()
            text = (product["description"] + " " +
                    " ".join(product.get("keywords", []))).lower()
            score = 0
            for term in terms:
                if term in name:
                    score += 2
                if term in text:
                    score += 1
            if terms and score == 0:
                continue
            scored.append((score, product))
        scored.sort(key=lambda s: (-s[0], s[1]["product_id"]))
        return [p for _, p in scored]

    def freshness_status(self, product, as_of):
        """'fresh' or 'stale' from last_updated + the freshness SLA.

        as_of and last_updated are datetimes. A product with no
        last_updated is stale.
        """
        updated = product.get("last_updated")
        if not updated:
            return "stale"
        deadline = updated + timedelta(hours=product["freshness_sla_hours"])
        return "fresh" if as_of <= deadline else "stale"

    def check_access(self, product, role):
        """Governed access: restricted products need a steward/admin role."""
        if product["access_level"] == "restricted":
            return role in RESTRICTED_ROLES
        if product["access_level"] == "internal":
            return role != "external"
        return True

    def lineage(self, product_id):
        """Lineage entries tracing the product to source and transform."""
        if product_id not in self._products:
            raise RegistryError(f"unknown product_id: {product_id}")
        return list(self._lineage.get(product_id, []))

    def product_card(self, product):
        """One-dict summary a UI or API renders per product."""
        return {
            "product_id": product["product_id"],
            "name": product["name"],
            "domain": product["domain"],
            "owner": product["owner"],
            "version": product["version"],
            "quality_score": product["quality_score"],
            "access_level": product["access_level"],
            "status": product["status"],
            "fields": [f["name"] for f in product["schema"]],
        }
