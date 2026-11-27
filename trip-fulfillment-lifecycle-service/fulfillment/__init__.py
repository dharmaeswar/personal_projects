"""Trip fulfillment lifecycle service.

A backend platform service modelling the trip fulfillment flow Uber's
Fulfillment Platform describes: shopping, ordering, matching & dispatching,
and tracking phases for orders/trips, with pricing, matching and dynamics
integrated into the lifecycle. All data is synthetic and seeded; nothing
here describes a real Uber system, real trips, or real fares.
"""

from fulfillment.lifecycle import Trip, TripState, transition
from fulfillment.pricing import FareQuote, quote_fare
from fulfillment.matching import Driver, match_driver
from fulfillment.service import FulfillmentService

__all__ = [
    "Trip",
    "TripState",
    "transition",
    "FareQuote",
    "quote_fare",
    "Driver",
    "match_driver",
    "FulfillmentService",
]
