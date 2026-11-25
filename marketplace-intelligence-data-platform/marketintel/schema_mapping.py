"""AI-assisted schema mapping with confidence scoring, structured-output
validation, and a human-review queue.

The mapper proposes a mapping from a source record's fields to the
target schema and scores every field:

- 1.00 exact field-name match
- 0.85 known synonym (curated dictionary, e.g. fare_usd -> price_usd)
- 0.60 normalised fuzzy match (case/underscore-insensitive containment)
- 0.00 unmapped (field dropped, recorded, never guessed)

Structured-output validation then checks the mapped record against the
target schema: every required field present, every value coercible to
its declared type, enum values in range. A record that fails validation
is quarantined, not loaded.

Fields mapped below REVIEW_THRESHOLD (0.70) go to a human-review queue
instead of being applied silently. In production the mapping proposals
would come from an LLM; this deterministic mapper implements the same
interface (propose -> score -> validate -> review-gate), so the
confidence, validation and review gates are the safeguards that make an
LLM's output safe to load. No LLM is called here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REVIEW_THRESHOLD = 0.70

# Target schema: field -> (python type, required, allowed values or None)
TARGET_SCHEMA = {
    "competitor": (str, True, None),
    "zone": (str, True, None),
    "snapshot_date": (str, True, None),
    "price_usd": (float, True, None),
    "demand_index": (float, False, None),
    "surge_multiplier": (float, False, None),
    "service": (str, False, ("ride", "delivery")),
}

FIELD_SYNONYMS = {
    # v2 feed renamed price_usd -> fare_usd; v1 used cost_usd in one feed.
    "fare_usd": "price_usd",
    "cost_usd": "price_usd",
    "amount_usd": "price_usd",
    "provider": "competitor",
    "competitor_name": "competitor",
    "area": "zone",
    "zone_id": "zone",
    "date": "snapshot_date",
    "day": "snapshot_date",
    "demand": "demand_index",
    "demand_score": "demand_index",
    "surge": "surge_multiplier",
    "product": "service",
    "service_type": "service",
}


def _normalise(name):
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def propose_mapping(source_fields):
    """Return {source_field: (target_field, confidence)} for each field
    that maps, plus a list of unmapped source fields."""
    mapping = {}
    unmapped = []
    for src in source_fields:
        norm = _normalise(src)
        if norm in TARGET_SCHEMA:
            mapping[src] = (norm, 1.00)
        elif norm in FIELD_SYNONYMS:
            mapping[src] = (FIELD_SYNONYMS[norm], 0.85)
        else:
            # Fuzzy: a target field name contained in the source name
            # (or vice versa) after normalisation.
            hit = None
            for target in TARGET_SCHEMA:
                if target in norm or norm in target:
                    hit = target
                    break
            if hit:
                mapping[src] = (hit, 0.60)
            else:
                unmapped.append(src)
    return mapping, unmapped


@dataclass
class MappingReport:
    mapped: dict
    field_confidence: dict
    unmapped: list
    needs_review: list  # (source_field, target_field, confidence)
    validation_errors: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.validation_errors


def _coerce(value, pytype):
    if value is None or value == "":
        return None
    if pytype is float:
        return float(value)
    if pytype is str:
        return str(value).strip()
    return value


def map_record(payload, source_fields=None):
    """Map one raw payload to the target schema. Returns
    (mapped_dict, MappingReport)."""
    fields = list(payload.keys()) if source_fields is None else source_fields
    mapping, unmapped = propose_mapping(fields)
    mapped = {}
    confidence = {}
    needs_review = []
    for src, (target, conf) in mapping.items():
        mapped[target] = payload.get(src)
        confidence[target] = conf
        if conf < REVIEW_THRESHOLD:
            needs_review.append((src, target, conf))
    errors = validate_mapped(mapped)
    return mapped, MappingReport(
        mapped=mapped,
        field_confidence=confidence,
        unmapped=unmapped,
        needs_review=needs_review,
        validation_errors=errors,
    )


def validate_mapped(mapped):
    """Structured-output validation: required fields, types, enums.
    Returns a list of error strings (empty = valid). Coercion failures
    are errors, not silent drops."""
    errors = []
    for name, (pytype, required, allowed) in TARGET_SCHEMA.items():
        value = mapped.get(name)
        if value is None or value == "":
            if required:
                errors.append(f"missing required field: {name}")
            continue
        try:
            coerced = _coerce(value, pytype)
        except (TypeError, ValueError):
            errors.append(f"field {name} not coercible to {pytype.__name__}: {value!r}")
            continue
        mapped[name] = coerced
        if allowed is not None and coerced not in allowed:
            errors.append(f"field {name} value {coerced!r} not in {allowed}")
        if pytype is float and name == "price_usd" and coerced is not None and coerced <= 0:
            errors.append(f"field price_usd must be > 0, got {coerced}")
    return errors


class ReviewQueue:
    """Human-review queue for low-confidence mappings. A reviewer
    confirms or corrects a proposed mapping; confirmed mappings are
    recorded so the same source field is never re-queued."""

    def __init__(self):
        self.items = []  # dicts: source_field, target_field, confidence, status
        self.confirmed = {}  # source_field -> target_field

    def add(self, source_field, target_field, confidence, record_ref=""):
        if source_field in self.confirmed:
            return False
        self.items.append(
            {
                "source_field": source_field,
                "target_field": target_field,
                "confidence": confidence,
                "record_ref": record_ref,
                "status": "pending",
            }
        )
        return True

    def confirm(self, source_field, target_field):
        self.confirmed[source_field] = target_field
        for item in self.items:
            if item["source_field"] == source_field:
                item["status"] = "confirmed"

    def pending(self):
        return [i for i in self.items if i["status"] == "pending"]
