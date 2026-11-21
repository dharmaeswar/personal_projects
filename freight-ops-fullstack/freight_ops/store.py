"""Freight Ops — full-stack rail shipment tracking (demo project).

In-memory store for rail freight shipments and their tracking events.
All data is synthetic; nothing here talks to a real railroad system.
"""

import itertools
import re
from datetime import datetime, timezone

STATUSES = ("booked", "in_transit", "delayed", "delivered")
EVENT_TYPES = ("departed", "arrived_yard", "delayed", "delivered")

_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{2,23}$")

_id_counter = itertools.count(1)


class ValidationError(ValueError):
    """Raised when a shipment or event payload fails validation."""


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_str(body, field, min_len=1, max_len=80):
    value = body.get(field)
    if not isinstance(value, str) or not min_len <= len(value.strip()) <= max_len:
        raise ValidationError(f"{field} must be a string of {min_len}-{max_len} characters")
    return value.strip()


def _require_int(body, field, low, high):
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{field} must be an integer between {low} and {high}")
    return value


def _require_number(body, field, low, high):
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low < value <= high:
        raise ValidationError(f"{field} must be a number greater than {low} and at most {high}")
    return float(value)


def validate_shipment(body):
    """Validate a create-shipment payload; return a cleaned dict."""
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    reference = _require_str(body, "reference", 3, 24)
    if not _REFERENCE_RE.match(reference):
        raise ValidationError("reference must be 3-24 letters, digits or hyphens")
    return {
        "reference": reference,
        "origin": _require_str(body, "origin", 2, 80),
        "destination": _require_str(body, "destination", 2, 80),
        "cars": _require_int(body, "cars", 1, 200),
        "weight_tons": _require_number(body, "weight_tons", 0, 20000),
        "distance_miles": _require_number(body, "distance_miles", 0, 10000),
    }


def validate_event(body):
    """Validate an append-event payload; return a cleaned dict."""
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    event_type = body.get("type")
    if event_type not in EVENT_TYPES:
        raise ValidationError(f"type must be one of {', '.join(EVENT_TYPES)}")
    return {
        "type": event_type,
        "location": _require_str(body, "location", 2, 80),
        "note": _require_str(body, "note", 0, 200) if body.get("note") else "",
    }


class ShipmentStore:
    """In-memory shipment store. One instance per service process."""

    def __init__(self):
        self._shipments = {}
        self._order = []

    def create(self, cleaned):
        shipment_id = next(_id_counter)
        shipment = {
            "id": shipment_id,
            "reference": cleaned["reference"],
            "origin": cleaned["origin"],
            "destination": cleaned["destination"],
            "cars": cleaned["cars"],
            "weight_tons": cleaned["weight_tons"],
            "distance_miles": cleaned["distance_miles"],
            "distance_remaining_miles": cleaned["distance_miles"],
            "status": "booked",
            "created_at": _now_iso(),
            "events": [],
        }
        self._shipments[shipment_id] = shipment
        self._order.append(shipment_id)
        return shipment

    def get(self, shipment_id):
        return self._shipments.get(shipment_id)

    def list(self, status=None):
        shipments = [self._shipments[sid] for sid in self._order]
        if status is not None:
            if status not in STATUSES:
                raise ValidationError(f"status must be one of {', '.join(STATUSES)}")
            shipments = [s for s in shipments if s["status"] == status]
        return shipments

    def add_event(self, shipment_id, cleaned):
        shipment = self._shipments.get(shipment_id)
        if shipment is None:
            return None
        event = {
            "type": cleaned["type"],
            "location": cleaned["location"],
            "note": cleaned["note"],
            "recorded_at": _now_iso(),
        }
        shipment["events"].append(event)
        if cleaned["type"] == "departed" and shipment["status"] == "booked":
            shipment["status"] = "in_transit"
        elif cleaned["type"] == "delayed":
            shipment["status"] = "delayed"
        elif cleaned["type"] == "delivered":
            shipment["status"] = "delivered"
            shipment["distance_remaining_miles"] = 0.0
        return shipment

    def update_progress(self, shipment_id, distance_remaining_miles):
        """Advance a shipment along its route (synthetic progress input)."""
        shipment = self._shipments.get(shipment_id)
        if shipment is None:
            return None
        if not isinstance(distance_remaining_miles, (int, float)) or isinstance(
            distance_remaining_miles, bool
        ):
            raise ValidationError("distance_remaining_miles must be a number")
        if not 0 <= distance_remaining_miles <= shipment["distance_miles"]:
            raise ValidationError(
                "distance_remaining_miles must be between 0 and distance_miles"
            )
        shipment["distance_remaining_miles"] = float(distance_remaining_miles)
        if shipment["status"] == "delayed" and distance_remaining_miles == 0:
            shipment["status"] = "delivered"
        return shipment

    def dashboard(self):
        counts = {status: 0 for status in STATUSES}
        delivered = 0
        delivered_on_time = 0
        total_cars = 0
        for shipment in self._shipments.values():
            counts[shipment["status"]] += 1
            total_cars += shipment["cars"]
            if shipment["status"] == "delivered":
                delivered += 1
                if not any(e["type"] == "delayed" for e in shipment["events"]):
                    delivered_on_time += 1
        on_time_rate = (delivered_on_time / delivered) if delivered else None
        return {
            "total_shipments": len(self._shipments),
            "by_status": counts,
            "total_cars": total_cars,
            "delivered": delivered,
            "on_time_rate": on_time_rate,
        }
