"""ETA estimates for freight shipments (demo planning math).

A shipment's ETA is distance remaining divided by a planning speed.
The default 28 mph is a planning assumption for freight rail, stated in
the README — not a measured average. A delayed shipment gets a 25%
buffer because a delay usually means waiting for a yard slot or crew.
"""

DEFAULT_SPEED_MPH = 28.0
DELAY_BUFFER = 1.25


def estimate_eta_hours(shipment, speed_mph=DEFAULT_SPEED_MPH):
    """Estimated hours until delivery for one shipment dict."""
    if speed_mph <= 0:
        raise ValueError("speed_mph must be positive")
    remaining = shipment["distance_remaining_miles"]
    if remaining <= 0:
        return 0.0
    hours = remaining / speed_mph
    if shipment["status"] == "delayed":
        hours *= DELAY_BUFFER
    return round(hours, 2)


def estimate_eta(shipment, speed_mph=DEFAULT_SPEED_MPH):
    """Full ETA payload for the API: hours plus the inputs used."""
    return {
        "shipment_id": shipment["id"],
        "reference": shipment["reference"],
        "status": shipment["status"],
        "distance_remaining_miles": shipment["distance_remaining_miles"],
        "planning_speed_mph": speed_mph,
        "delay_buffer_applied": shipment["status"] == "delayed",
        "eta_hours": estimate_eta_hours(shipment, speed_mph),
    }
