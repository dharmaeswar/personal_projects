"""Distributor data-integrity rules.

Each rule returns a violation string or None. A shipment that fails any
rule is quarantined with every rule that caught it; nothing invalid
reaches the warehouse. Rules mirror the posting's duties: data integrity,
dimensional-model inputs, and unit-testable checks.
"""

WINDOW_START = "2026-01-01"
WINDOW_END = "2026-12-31"
AMOUNT_TOLERANCE = 0.01


def rule_no_duplicate(shipment, ctx):
    """R1: no duplicate shipment_id in the batch."""
    if shipment["shipment_id"] in ctx["seen_shipment_ids"]:
        return "duplicate shipment_id %s in batch" % shipment["shipment_id"]
    return None


def rule_positive_quantity(shipment, ctx):
    """R2: quantity must be positive."""
    if shipment["quantity"] <= 0:
        return "quantity %s is not positive" % shipment["quantity"]
    return None


def rule_product_known(shipment, ctx):
    """R3: product must exist in the inventory master."""
    if shipment["product_id"] not in ctx["inventory"]:
        return "unknown product_id %s (not in inventory master)" \
            % shipment["product_id"]
    return None


def rule_amount_matches_pricing(shipment, ctx):
    """R4: amount must equal quantity x unit price from inventory."""
    product = ctx["inventory"].get(shipment["product_id"])
    if product is None:
        return None  # already caught by R3; do not double-report
    expected = shipment["quantity"] * product["unit_price"]
    if abs(shipment["amount"] - expected) > AMOUNT_TOLERANCE:
        return ("amount %.2f does not match quantity x unit price %.2f"
                % (shipment["amount"], expected))
    return None


def rule_customer_active(shipment, ctx):
    """R5: customer must be active and under contract on the ship date."""
    customer = ctx["customers"].get(shipment["customer_id"])
    if customer is None:
        return "unknown customer_id %s" % shipment["customer_id"]
    if customer["active"] != "Y":
        return "customer %s is not active" % shipment["customer_id"]
    if not (customer["contract_start"] <= shipment["ship_date"]
            <= customer["contract_end"]):
        return ("ship date %s outside contract %s..%s for customer %s"
                % (shipment["ship_date"], customer["contract_start"],
                   customer["contract_end"], shipment["customer_id"]))
    return None


def rule_ship_date_in_window(shipment, ctx):
    """R6: ship date must fall inside the reporting window."""
    if not (WINDOW_START <= shipment["ship_date"] <= WINDOW_END):
        return ("ship date %s outside reporting window %s..%s"
                % (shipment["ship_date"], WINDOW_START, WINDOW_END))
    return None


RULES = (rule_no_duplicate, rule_positive_quantity, rule_product_known,
         rule_amount_matches_pricing, rule_customer_active,
         rule_ship_date_in_window)


def validate_shipment(shipment, ctx):
    """Return the list of violations for one shipment (empty = valid)."""
    violations = [v for rule in RULES for v in [rule(shipment, ctx)] if v]
    ctx["seen_shipment_ids"].add(shipment["shipment_id"])
    return violations


def validate_batch(shipments, inventory, customers):
    """Split shipments into (valid, quarantined) with reasons per row."""
    ctx = {"inventory": inventory, "customers": customers,
           "seen_shipment_ids": set()}
    valid, quarantined = [], []
    for shipment in shipments:
        violations = validate_shipment(shipment, ctx)
        if violations:
            quarantined.append({"shipment": shipment,
                                "violations": violations})
        else:
            valid.append(shipment)
    return valid, quarantined
