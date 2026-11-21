"""Deterministic synthetic product catalog for the catalog-quality checks.

Eighteen invented listings across four categories. Nine quality problems
are planted on purpose so the checks have real defects to catch; nothing
here is a real listing, seller or price.

Planted defects:
1. CAT-001 has no brand (completeness).
2. CAT-002 is priced $0.00 (attribute consistency).
3. CAT-003 and CAT-004 are the same product listed twice (duplicate).
4. CAT-005 titles a Nike shoe but its brand field says Adidas (consistency).
5. CAT-006 is priced $1,299.99 in a category whose median is ~$60 (outlier).
6. CAT-007, an apparel listing, is missing its required "size" attribute.
7. CAT-008 is priced in EUR on the US marketplace (consistency).
8. CAT-009 has an unparseable price, "call for price" (consistency).
9. CAT-010 is missing its required "model" attribute (electronics).

The feedback events show the self-learning loop at work: sellers accepted
9 of 10 brand-alias corrections (trusted rule) but rejected 3 of 5
price-outlier flags (untrusted rule), so only the brand rule may
auto-correct. The labeled correction set scores 9 of 10 correct, so the
evaluation guardrail passes at the 0.90 precision bar.
"""

# (rule_id, accepted?) — one entry per seller verdict.
FEEDBACK_EVENTS = (
    [("brand-alias", True)] * 9 + [("brand-alias", False)]
    + [("price-outlier-flag", True)] * 2 + [("price-outlier-flag", False)] * 3
    + [("unit-standardize", True)] * 5
)

# (record_id, signal_type) — customer signals against listings.
CUSTOMER_SIGNALS = [
    ("CAT-007", "wrong-size-report"),
    ("CAT-007", "wrong-size-report"),
    ("CAT-007", "wrong-size-report"),
    ("CAT-005", "wrong-brand-report"),
    ("CAT-005", "wrong-brand-report"),
]

# Proposed auto-corrections: (record_id, field, new_value, rule_id).
PROPOSED_CORRECTIONS = [
    {"record_id": "CAT-011", "field": "brand", "new_value": "Nike",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-012", "field": "brand", "new_value": "Apple",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-013", "field": "brand", "new_value": "Samsung",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-014", "field": "brand", "new_value": "Levi's",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-015", "field": "brand", "new_value": "Adidas",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-016", "field": "brand", "new_value": "Nike",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-017", "field": "brand", "new_value": "Apple",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-018", "field": "brand", "new_value": "Samsung",
     "rule_id": "brand-alias"},
    {"record_id": "CAT-006", "field": "price", "new_value": 59.99,
     "rule_id": "price-outlier-flag"},
    {"record_id": "CAT-008", "field": "currency", "new_value": "USD",
     "rule_id": "price-outlier-flag"},
]

# Known-correct values for the proposed corrections. CAT-016's true brand
# is Puma, not Nike, so that one proposed correction is wrong on purpose:
# 9 of 10 correct, precision 0.900, and the guardrail passes.
CORRECTION_LABELS = {
    ("CAT-011", "brand"): "Nike",
    ("CAT-012", "brand"): "Apple",
    ("CAT-013", "brand"): "Samsung",
    ("CAT-014", "brand"): "Levi's",
    ("CAT-015", "brand"): "Adidas",
    ("CAT-016", "brand"): "Puma",
    ("CAT-017", "brand"): "Apple",
    ("CAT-018", "brand"): "Samsung",
    ("CAT-006", "price"): 59.99,
    ("CAT-008", "currency"): "USD",
}


def build_catalog():
    """Build the synthetic 18-product catalog."""
    return [
        {"id": "CAT-001", "title": "Stainless Steel Water Bottle 1L",
         "brand": "", "category": "home", "price": 24.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-a",
         "attributes": {"material": "steel", "color": "silver"}},
        {"id": "CAT-002", "title": "Wireless Mouse", "brand": "LogiTech",
         "category": "electronics", "price": 0.00, "currency": "USD",
         "marketplace": "US", "seller_id": "seller-b",
         "attributes": {"model": "M220", "color": "black"}},
        {"id": "CAT-003", "title": "  Nike   Air Zoom Running Shoes ",
         "brand": "nike inc.", "category": "apparel", "price": 89.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-c",
         "attributes": {"size": "10", "color": "white"}},
        {"id": "CAT-004", "title": "Nike Air Zoom Running Shoes",
         "brand": "NIKE", "category": "apparel", "price": 89.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-d",
         "attributes": {"size": "10", "color": "white"}},
        {"id": "CAT-005", "title": "Nike Air Max Running Shoes",
         "brand": "Adidas", "category": "apparel", "price": 119.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-e",
         "attributes": {"size": "9", "color": "black"}},
        {"id": "CAT-006", "title": "Cotton Crew Socks 6-Pack",
         "brand": "Hanes", "category": "apparel", "price": "1,299.99 USD",
         "currency": "USD", "marketplace": "US", "seller_id": "seller-f",
         "attributes": {"size": "M", "color": "white"}},
        {"id": "CAT-007", "title": "Mens Slim Fit Jeans",
         "brand": "Levi's", "category": "apparel", "price": 59.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-g",
         "attributes": {"color": "blue"}},
        {"id": "CAT-008", "title": "Organic Green Tea 100 Bags",
         "brand": "Twinings", "category": "grocery", "price": "8.49 EUR",
         "currency": "EUR", "marketplace": "US", "seller_id": "seller-h",
         "attributes": {"weight": "200 g"}},
        {"id": "CAT-009", "title": "Bluetooth Speaker", "brand": "JBL",
         "category": "electronics", "price": "call for price",
         "currency": "USD", "marketplace": "US", "seller_id": "seller-i",
         "attributes": {"model": "Flip 6", "color": "blue"}},
        {"id": "CAT-010", "title": "4K Action Camera", "brand": "GoPro",
         "category": "electronics", "price": 299.99, "currency": "USD",
         "marketplace": "US", "seller_id": "seller-j",
         "attributes": {"color": "black"}},
        {"id": "CAT-011", "title": "Air Zoom Pegasus 40",
         "brand": "nike inc", "category": "apparel", "price": 129.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-k",
         "attributes": {"size": "11", "color": "grey"}},
        {"id": "CAT-012", "title": "iPhone 15 Case", "brand": "apple inc.",
         "category": "electronics", "price": 29.99, "currency": "USD",
         "marketplace": "US", "seller_id": "seller-l",
         "attributes": {"model": "A2846", "color": "clear"}},
        {"id": "CAT-013", "title": "Galaxy Buds 2 Pro",
         "brand": "samsung electronics", "category": "electronics",
         "price": 179.99, "currency": "USD", "marketplace": "US",
         "seller_id": "seller-m",
         "attributes": {"model": "SM-R510", "color": "white"}},
        {"id": "CAT-014", "title": "501 Original Fit Jeans",
         "brand": "levi strauss", "category": "apparel", "price": 69.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-n",
         "attributes": {"size": "32", "color": "indigo"}},
        {"id": "CAT-015", "title": "Ultraboost Light Shoes",
         "brand": "adidas ag", "category": "apparel", "price": 139.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-o",
         "attributes": {"size": "10", "color": "white"}},
        {"id": "CAT-016", "title": "RS-X Reinvention Sneakers",
         "brand": "Puma", "category": "apparel", "price": 99.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-p",
         "attributes": {"size": "9", "color": "red"}},
        {"id": "CAT-017", "title": "AirPods Pro 2nd Gen",
         "brand": "APPLE", "category": "electronics", "price": 199.99,
         "currency": "USD", "marketplace": "US", "seller_id": "seller-q",
         "attributes": {"model": "A2698", "color": "white"}},
        {"id": "CAT-018", "title": "Galaxy Watch 6", "brand": "SAMSUNG",
         "category": "electronics", "price": 249.99, "currency": "USD",
         "marketplace": "US", "seller_id": "seller-r",
         "attributes": {"model": "SM-R930", "color": "black"}},
    ]
