"""Catalog quality: normalization, defect checks, self-learning feedback.

Extends the data-quality pipeline to a product catalog, the way Amazon's
Catalog System Services team works: normalize product attributes, detect
catalog defects, learn from seller feedback and customer signals, and gate
automated corrections behind an evaluation guardrail.

A product is a dict with keys: id, title, brand, category, price, currency,
marketplace, seller_id, attributes (dict, e.g. size, color, model, weight).
A finding is a dict with keys: check, severity, record_id, detail — the
same shape as the checks in checks.py.
"""

import re
from collections import Counter, defaultdict

# Required attributes per category; a listing missing one is incomplete.
REQUIRED_ATTRIBUTES = {
    "apparel": ("size", "color"),
    "electronics": ("model",),
    "grocery": ("weight",),
    "home": ("material",),
}

# Known brand spellings seen in seller feeds, mapped to the canonical name.
BRAND_ALIASES = {
    "nike inc.": "Nike",
    "nike inc": "Nike",
    "nike": "Nike",
    "adidas ag": "Adidas",
    "adidas": "Adidas",
    "apple inc.": "Apple",
    "apple inc": "Apple",
    "apple": "Apple",
    "samsung electronics": "Samsung",
    "samsung": "Samsung",
    "levis": "Levi's",
    "levi strauss": "Levi's",
}

_WEIGHT_UNITS = {"g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}
_PRICE_RE = re.compile(r"^\$?\s*([0-9][0-9,]*\.?[0-9]*)\s*([A-Za-z]{3})?$")
_WEIGHT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*(g|kg|oz|lb)$", re.IGNORECASE)


def _finding(check, severity, record_id, detail):
    return {
        "check": check,
        "severity": severity,
        "record_id": record_id,
        "detail": detail,
    }


def normalize_title(title):
    """Collapse whitespace and title-case a product title."""
    words = re.sub(r"\s+", " ", (title or "").strip()).split(" ")
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def normalize_brand(brand):
    """Map a seller-supplied brand spelling to its canonical name."""
    key = re.sub(r"\s+", " ", (brand or "").strip().lower())
    if key in BRAND_ALIASES:
        return BRAND_ALIASES[key]
    return normalize_title(brand)


def normalize_price(raw):
    """Parse a price like 12.99, "$12.99" or "12.99 USD" to (amount, currency).

    Returns (None, None) when the value cannot be parsed.
    """
    if isinstance(raw, (int, float)):
        return float(raw), "USD"
    match = _PRICE_RE.match(str(raw or "").strip())
    if not match:
        return None, None
    amount = float(match.group(1).replace(",", ""))
    currency = (match.group(2) or "USD").upper()
    return amount, currency


def normalize_weight(raw):
    """Convert a weight like "340 g", "12 oz" or "1.5 kg" to grams.

    Returns None when the value cannot be parsed.
    """
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _WEIGHT_RE.match(str(raw or "").strip())
    if not match:
        return None
    return round(float(match.group(1)) * _WEIGHT_UNITS[match.group(2).lower()], 2)


def normalize_product(product):
    """Return a normalized copy of a product record.

    Adds title_norm, brand_norm, price_amount, price_currency and
    weight_g; attribute keys are lowercased.
    """
    amount, currency = normalize_price(product.get("price"))
    attrs = {
        str(k).lower(): v for k, v in (product.get("attributes") or {}).items()
    }
    normalized = dict(product)
    normalized["title_norm"] = normalize_title(product.get("title"))
    normalized["brand_norm"] = normalize_brand(product.get("brand"))
    normalized["price_amount"] = amount
    normalized["price_currency"] = currency
    normalized["weight_g"] = normalize_weight(attrs.get("weight"))
    normalized["attributes"] = attrs
    return normalized


def check_catalog_completeness(products):
    """Every listing needs a title, brand, category and price, plus the
    attributes its category requires."""
    findings = []
    for prod in products:
        pid = prod.get("id")
        for field in ("title", "brand", "category"):
            if not (prod.get(field) or "").strip():
                findings.append(
                    _finding("catalog-completeness", "critical", pid,
                             "missing %s" % field)
                )
        if prod.get("price") in (None, ""):
            findings.append(
                _finding("catalog-completeness", "critical", pid,
                         "missing price")
            )
        for attr in REQUIRED_ATTRIBUTES.get(prod.get("category"), ()):
            if attr not in (prod.get("attributes") or {}):
                findings.append(
                    _finding("catalog-completeness", "critical", pid,
                             "category %r requires attribute %r"
                             % (prod.get("category"), attr))
                )
    return findings


def check_attribute_consistency(products):
    """Prices must be positive and in the marketplace currency; a price far
    above its category median is flagged; the title must not name a
    different known brand than the brand field."""
    findings = []
    normalized = [normalize_product(p) for p in products]
    medians = {}
    by_category = defaultdict(list)
    for prod in normalized:
        if prod["price_amount"] is not None:
            by_category[prod.get("category")].append(prod["price_amount"])
    for category, prices in by_category.items():
        ordered = sorted(prices)
        medians[category] = ordered[len(ordered) // 2]
    for prod in normalized:
        pid = prod.get("id")
        amount = prod["price_amount"]
        if amount is None:
            findings.append(
                _finding("attribute-consistency", "critical", pid,
                         "price %r cannot be parsed" % (prod.get("price"),))
            )
        elif amount <= 0:
            findings.append(
                _finding("attribute-consistency", "critical", pid,
                         "price is %s, must be positive" % (amount,))
            )
        elif medians.get(prod.get("category")) and amount > 5 * medians[prod.get("category")]:
            findings.append(
                _finding("attribute-consistency", "warning", pid,
                         "price %s is over 5x the %s median of %s"
                         % (amount, prod.get("category"),
                            medians[prod.get("category")]))
            )
        if prod["price_currency"] not in (None, "USD"):
            findings.append(
                _finding("attribute-consistency", "warning", pid,
                         "currency %s is not the marketplace currency USD"
                         % (prod["price_currency"],))
            )
        title_lower = (prod.get("title") or "").lower()
        for alias, canonical in BRAND_ALIASES.items():
            if alias in title_lower and canonical != prod["brand_norm"]:
                findings.append(
                    _finding("attribute-consistency", "critical", pid,
                             "title names %r but brand field is %r"
                             % (canonical, prod.get("brand")))
                )
                break
    return findings


def check_duplicate_listings(products):
    """Two listings with the same normalized brand, title and key
    attributes are the same product listed twice."""
    findings = []
    normalized = [normalize_product(p) for p in products]
    by_key = defaultdict(list)
    for prod in normalized:
        attrs = prod["attributes"]
        key_attrs = tuple(sorted(
            (k, str(v).lower()) for k, v in attrs.items() if k != "weight"
        ))
        key = (prod["brand_norm"].lower(), prod["title_norm"].lower(), key_attrs)
        by_key[key].append(prod.get("id"))
    for key, ids in by_key.items():
        if len(ids) > 1:
            findings.append(
                _finding("duplicate-listing", "critical", ids[0],
                         "same product as %s (brand %r, title %r)"
                         % (", ".join(ids[1:]), key[0], key[1]))
            )
    return findings


class FeedbackLoop:
    """Self-learning loop: seller feedback and customer signals update how
    much each correction rule is trusted, and only trusted rules may
    auto-correct listings.

    A rule's trust weight is its accepted share with Laplace smoothing:
    (accepted + 1) / (accepted + rejected + 2). A rule may auto-correct
    once its weight reaches the threshold and it has at least
    min_observations of feedback behind it.
    """

    def __init__(self, threshold=0.8, min_observations=3):
        self.threshold = threshold
        self.min_observations = min_observations
        self.rules = {}
        self.signals = Counter()

    def ingest_feedback(self, rule_id, accepted):
        """Record one seller verdict on a correction the rule proposed."""
        entry = self.rules.setdefault(rule_id, {"accepted": 0, "rejected": 0})
        if accepted:
            entry["accepted"] += 1
        else:
            entry["rejected"] += 1

    def ingest_signal(self, record_id, signal_type):
        """Record one customer signal (e.g. 'wrong-size-report') against a
        listing; repeated signals flag the listing for re-check."""
        self.signals[(record_id, signal_type)] += 1

    def weight(self, rule_id):
        entry = self.rules.get(rule_id, {"accepted": 0, "rejected": 0})
        total = entry["accepted"] + entry["rejected"]
        return round((entry["accepted"] + 1) / (total + 2), 3)

    def observations(self, rule_id):
        entry = self.rules.get(rule_id, {"accepted": 0, "rejected": 0})
        return entry["accepted"] + entry["rejected"]

    def should_auto_correct(self, rule_id):
        return (
            self.observations(rule_id) >= self.min_observations
            and self.weight(rule_id) >= self.threshold
        )

    def flagged_records(self, min_signals=2):
        """Listings with at least min_signals of the same customer signal."""
        totals = Counter()
        for (record_id, _signal), count in self.signals.items():
            totals[record_id] += count
        return sorted(rid for rid, count in totals.items() if count >= min_signals)

    def apply_corrections(self, products, corrections):
        """Apply proposed corrections whose rule is trusted; block the rest.

        A correction is a dict: record_id, field, new_value, rule_id.
        Returns (updated_products, applied, blocked) where applied/blocked
        are lists of the correction dicts with a 'status' key added.
        """
        by_id = {p.get("id"): dict(p) for p in products}
        applied, blocked = [], []
        for corr in corrections:
            entry = dict(corr)
            if self.should_auto_correct(corr["rule_id"]):
                target = by_id.get(corr["record_id"])
                if target is not None:
                    target[corr["field"]] = corr["new_value"]
                entry["status"] = "applied"
                applied.append(entry)
            else:
                entry["status"] = "blocked"
                blocked.append(entry)
        return [by_id[p.get("id")] for p in products], applied, blocked


def evaluate_corrections(proposed, labels, min_precision=0.9):
    """Score proposed auto-corrections against known-correct values.

    proposed: list of (record_id, field, new_value).
    labels: dict (record_id, field) -> correct value.
    Returns precision, recall and a PASS/FAIL gate: the rollout is
    blocked when precision falls below min_precision.
    """
    correct = sum(
        1 for rid, field, value in proposed
        if labels.get((rid, field)) == value
    )
    total_proposed = len(proposed)
    total_needed = len(labels)
    precision = round(correct / total_proposed, 3) if total_proposed else 1.0
    recall = round(correct / total_needed, 3) if total_needed else 1.0
    return {
        "proposed": total_proposed,
        "correct": correct,
        "precision": precision,
        "recall": recall,
        "gate": "PASS" if precision >= min_precision else "FAIL",
    }


def run_catalog_checks(products):
    """Run every catalog check and return a report dict with a gate."""
    findings = (
        check_catalog_completeness(products)
        + check_attribute_consistency(products)
        + check_duplicate_listings(products)
    )
    critical = sum(1 for f in findings if f["severity"] == "critical")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    by_check = Counter(f["check"] for f in findings)
    return {
        "summary": {
            "total_products": len(products),
            "total_findings": len(findings),
            "critical": critical,
            "warnings": warnings,
            "findings_by_check": dict(by_check),
            "gate": "FAIL" if critical else "PASS",
        },
        "findings": findings,
    }
