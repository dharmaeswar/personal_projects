"""340B validation rules.

Each rule returns a violation string or None. A claim that fails any rule
is quarantined with every rule that caught it; nothing invalid reaches
the warehouse. Rules mirror the posting's validation duties: patient
eligibility, drug utilisation, and TPA capture.
"""

MAX_DAYS_SUPPLY = 90
MAX_DAILY_UNITS = 4  # at most 4 units per day of supply
AMOUNT_TOLERANCE = 0.01


def _eligible_on(elig, fill_date):
    if elig is None:
        return False
    if elig["eligible"] != "Y":
        return False
    return elig["start_date"] <= fill_date <= elig["end_date"]


def rule_eligibility(claim, ctx):
    """R1: patient must be covered-entity eligible on the fill date."""
    if not _eligible_on(ctx["eligibility"].get(claim["patient_id"]),
                         claim["fill_date"]):
        return ("patient %s not 340B-eligible on %s"
                % (claim["patient_id"], claim["fill_date"]))
    return None


def rule_ndc_format(claim, ctx):
    """R2: NDC must be 11 digits."""
    ndc = claim["ndc"]
    if len(ndc) != 11 or not ndc.isdigit():
        return "NDC %r is not an 11-digit code" % ndc
    return None


def rule_utilisation(claim, ctx):
    """R3: quantity and days-supply bounds (drug utilisation)."""
    if claim["quantity"] <= 0:
        return "quantity %s is not positive" % claim["quantity"]
    if not 1 <= claim["days_supply"] <= MAX_DAYS_SUPPLY:
        return ("days_supply %s outside 1-%d"
                % (claim["days_supply"], MAX_DAYS_SUPPLY))
    if claim["quantity"] > claim["days_supply"] * MAX_DAILY_UNITS:
        return ("quantity %s exceeds %d units/day for %s days supply"
                % (claim["quantity"], MAX_DAILY_UNITS, claim["days_supply"]))
    return None


def rule_amount_matches_pricing(claim, ctx):
    """R4: amount must equal quantity x unit price from the pricing feed."""
    price = ctx["pricing"].get(claim["ndc"])
    if price is None:
        return "no pricing record for NDC %s" % claim["ndc"]
    expected = claim["quantity"] * price["unit_price"]
    if abs(claim["amount"] - expected) > AMOUNT_TOLERANCE:
        return ("amount %.2f does not match quantity x unit price %.2f"
                % (claim["amount"], expected))
    return None


def rule_no_duplicate(claim, ctx):
    """R5: no duplicate claim_id in the batch."""
    if claim["claim_id"] in ctx["seen_claim_ids"]:
        return "duplicate claim_id %s in batch" % claim["claim_id"]
    return None


def rule_tpa_capture(claim, ctx):
    """R6: the 340B TPA must have captured the claim."""
    if claim["claim_id"] not in ctx["tpa_claim_ids"]:
        return "no 340B TPA capture for claim %s" % claim["claim_id"]
    return None


RULES = (rule_eligibility, rule_ndc_format, rule_utilisation,
         rule_amount_matches_pricing, rule_no_duplicate, rule_tpa_capture)


def validate_claim(claim, ctx):
    """Return the list of violations for one claim (empty = valid)."""
    violations = [v for rule in RULES for v in [rule(claim, ctx)] if v]
    ctx["seen_claim_ids"].add(claim["claim_id"])
    return violations


def validate_batch(claims, eligibility, pricing, tpa_captures):
    """Split claims into (valid, quarantined) with reasons per claim."""
    ctx = {"eligibility": eligibility, "pricing": pricing,
           "tpa_claim_ids": {c["claim_id"] for c in tpa_captures},
           "seen_claim_ids": set()}
    valid, quarantined = [], []
    for claim in claims:
        violations = validate_claim(claim, ctx)
        if violations:
            quarantined.append({"claim": claim, "violations": violations})
        else:
            valid.append(claim)
    return valid, quarantined
