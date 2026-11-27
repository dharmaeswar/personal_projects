"""Run a demo fulfillment flow end to end and print the trip + report."""

from fulfillment.pricing import quote_fare
from fulfillment.service import FulfillmentService, demo_drivers
from fulfillment.lifecycle import TripState


def main() -> None:
    service = FulfillmentService(demo_drivers())
    quote = quote_fare(distance_km=8.5, duration_min=22, surge_multiplier=1.25)
    print(f"Quote: ${quote.total_cents / 100:.2f} "
          f"(base {quote.base_cents} + distance {quote.distance_cents} "
          f"+ time {quote.time_cents}) x {quote.surge_multiplier} surge")
    trip = service.request_trip(
        "rider-42", "rider", 37.7749, -122.4194, 37.8049, -122.4494,
        quote, idempotency_key="demo-001")
    driver = service.match_and_dispatch(trip.trip_id)
    print(f"Matched driver {driver.driver_id} (rating {driver.rating})")
    service.advance(trip.trip_id, TripState.PICKUP)
    service.advance(trip.trip_id, TripState.IN_PROGRESS)
    service.advance(trip.trip_id, TripState.COMPLETED)
    trip = service.get_trip(trip.trip_id)
    print(f"Trip {trip.trip_id}: {' -> '.join(s.value for s in trip.history)}")
    print("Events:", len(service.events.events_for(trip.trip_id)))
    print("Reliability report:", service.reliability_report())


if __name__ == "__main__":
    main()
