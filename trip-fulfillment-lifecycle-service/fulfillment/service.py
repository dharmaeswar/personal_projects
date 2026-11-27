"""FulfillmentService: the platform orchestration over lifecycle + pricing
+ matching + events.

One service owns a trip end to end: quote the fare, request the trip,
match a driver, dispatch, track pickup and progress, and complete or
cancel it. Every step writes to the event log and enforces the state
machine, so a trip can never skip a phase or move after it is terminal.
Idempotency keys on request_trip mean a retried request returns the same
trip instead of creating a duplicate.
"""

from __future__ import annotations

import itertools
from datetime import datetime

from fulfillment.events import EventLog
from fulfillment.lifecycle import (
    IllegalTransitionError,
    Trip,
    TripState,
    transition,
)
from fulfillment.matching import Driver, match_driver
from fulfillment.pricing import FareQuote, quote_fare


class TripNotFoundError(KeyError):
    pass


class TripAlreadyTerminalError(ValueError):
    pass


class NoDriverAvailableError(ValueError):
    pass


class QuoteExpiredError(ValueError):
    pass


class FulfillmentService:
    def __init__(self, drivers: list[Driver] | None = None) -> None:
        self.drivers: list[Driver] = list(drivers or [])
        self.trips: dict[str, Trip] = {}
        self.events = EventLog()
        self._trip_seq = itertools.count(1)
        self._idempotency: dict[str, str] = {}

    # -- trip intake -------------------------------------------------
    def request_trip(self, rider_id: str, vertical: str,
                     pickup_lat: float, pickup_lon: float,
                     dropoff_lat: float, dropoff_lon: float,
                     quote: FareQuote, *,
                     idempotency_key: str | None = None) -> Trip:
        """Create a trip from a live (unexpired) fare quote."""
        if idempotency_key and idempotency_key in self._idempotency:
            return self.trips[self._idempotency[idempotency_key]]
        if quote.is_expired():
            raise QuoteExpiredError("fare quote expired; request a fresh quote")
        trip_id = f"trip-{next(self._trip_seq):06d}"
        trip = Trip(
            trip_id=trip_id, rider_id=rider_id, vertical=vertical,
            pickup_lat=pickup_lat, pickup_lon=pickup_lon,
            dropoff_lat=dropoff_lat, dropoff_lon=dropoff_lon,
            fare_cents=quote.total_cents,
        )
        self.trips[trip_id] = trip
        if idempotency_key:
            self._idempotency[idempotency_key] = trip_id
        self.events.append(trip_id, f"{trip_id}-created", "trip.requested",
                           f"vertical={vertical} fare_cents={quote.total_cents}")
        return trip

    def get_trip(self, trip_id: str) -> Trip:
        try:
            return self.trips[trip_id]
        except KeyError:
            raise TripNotFoundError(f"unknown trip {trip_id}") from None

    # -- matching & dispatch ----------------------------------------
    def match_and_dispatch(self, trip_id: str, *,
                           radius_km: float = 10.0,
                           min_seats: int = 1) -> Driver:
        """SEARCHING -> MATCHED -> DISPATCHED in one guarded step."""
        trip = self.get_trip(trip_id)
        if trip.is_terminal:
            raise TripAlreadyTerminalError(f"trip {trip_id} is {trip.state.value}")
        transition(trip, TripState.SEARCHING)
        self.events.append(trip_id, f"{trip_id}-searching", "trip.searching")
        driver = match_driver(self.drivers, trip.pickup_lat, trip.pickup_lon,
                              radius_km=radius_km, min_seats=min_seats)
        if driver is None:
            transition(trip, TripState.CANCELLED)
            self.events.append(trip_id, f"{trip_id}-no-driver",
                               "trip.cancelled", "no driver in radius")
            raise NoDriverAvailableError(f"no driver in radius for {trip_id}")
        trip.driver_id = driver.driver_id
        transition(trip, TripState.MATCHED)
        self.events.append(trip_id, f"{trip_id}-matched", "trip.matched",
                           f"driver={driver.driver_id}")
        transition(trip, TripState.DISPATCHED)
        self.events.append(trip_id, f"{trip_id}-dispatched", "trip.dispatched",
                           f"driver={driver.driver_id}")
        return driver

    # -- tracking ----------------------------------------------------
    def advance(self, trip_id: str, new_state: TripState) -> Trip:
        """Move a trip one legal step (pickup / in-progress / completed)."""
        trip = self.get_trip(trip_id)
        if trip.is_terminal:
            raise TripAlreadyTerminalError(f"trip {trip_id} is {trip.state.value}")
        transition(trip, new_state)
        self.events.append(trip_id, f"{trip_id}-{new_state.value}",
                           f"trip.{new_state.value}")
        return trip

    def cancel(self, trip_id: str, reason: str = "") -> Trip:
        trip = self.get_trip(trip_id)
        if trip.is_terminal:
            raise TripAlreadyTerminalError(f"trip {trip_id} is {trip.state.value}")
        transition(trip, TripState.CANCELLED)
        self.events.append(trip_id, f"{trip_id}-cancelled", "trip.cancelled",
                           reason)
        return trip

    # -- reporting ---------------------------------------------------
    def trips_by_state(self, state: TripState) -> list[Trip]:
        return [t for t in self.trips.values() if t.state == state]

    def reliability_report(self) -> dict:
        """Completion / cancellation counts per vertical, for ops review."""
        report: dict[str, dict[str, int]] = {}
        for trip in self.trips.values():
            bucket = report.setdefault(trip.vertical, {"completed": 0, "cancelled": 0, "active": 0})
            if trip.state == TripState.COMPLETED:
                bucket["completed"] += 1
            elif trip.state == TripState.CANCELLED:
                bucket["cancelled"] += 1
            else:
                bucket["active"] += 1
        return report


def demo_drivers() -> list[Driver]:
    """Seeded synthetic drivers around downtown San Francisco."""
    return [
        Driver("drv-001", 37.7749, -122.4194, 4.9, consecutive_trips=1),
        Driver("drv-002", 37.7849, -122.4094, 4.7, consecutive_trips=0),
        Driver("drv-003", 37.7649, -122.4294, 4.8, consecutive_trips=4),
        Driver("drv-004", 37.8049, -122.4494, 4.6, online=False),
        Driver("drv-005", 37.7549, -122.3994, 5.0, consecutive_trips=2, vehicle_seats=6),
    ]
