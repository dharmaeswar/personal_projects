import pytest

from fulfillment.events import EventLog
from fulfillment.lifecycle import TripState
from fulfillment.matching import Driver
from fulfillment.pricing import quote_fare
from fulfillment.service import (
    FulfillmentService,
    NoDriverAvailableError,
    QuoteExpiredError,
    TripAlreadyTerminalError,
    TripNotFoundError,
    demo_drivers,
)


def _service():
    return FulfillmentService(demo_drivers())


def _request(service, key=None):
    quote = quote_fare(8.0, 20.0)
    return service.request_trip(
        "rider-1", "rider", 37.7749, -122.4194, 37.8049, -122.4494,
        quote, idempotency_key=key)


def test_end_to_end_trip():
    service = _service()
    trip = _request(service)
    assert trip.state == TripState.REQUESTED
    assert trip.fare_cents == quote_fare(8.0, 20.0).total_cents
    driver = service.match_and_dispatch(trip.trip_id)
    assert driver.driver_id == "drv-001"
    assert trip.state == TripState.DISPATCHED
    service.advance(trip.trip_id, TripState.PICKUP)
    service.advance(trip.trip_id, TripState.IN_PROGRESS)
    service.advance(trip.trip_id, TripState.COMPLETED)
    assert service.get_trip(trip.trip_id).is_terminal
    events = service.events.events_for(trip.trip_id)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[0].event_type == "trip.requested"


def test_idempotent_retry_returns_same_trip():
    service = _service()
    first = _request(service, key="key-1")
    second = _request(service, key="key-1")
    assert first.trip_id == second.trip_id
    assert len(service.trips) == 1


def test_expired_quote_rejected():
    from datetime import datetime, timedelta
    service = _service()
    old = quote_fare(8.0, 20.0, now=datetime(2026, 11, 27, 10, 0, 0))
    # quote created at 10:00, expired at 10:05; request "now" is real time
    assert old.is_expired(datetime(2026, 11, 27, 10, 6, 0))
    with pytest.raises(QuoteExpiredError):
        service.request_trip("rider-1", "rider", 37.7749, -122.4194,
                             37.8049, -122.4494, old)


def test_no_driver_cancels_trip():
    service = FulfillmentService([Driver("far", 38.5, -122.0, 5.0)])
    trip = _request(service)
    with pytest.raises(NoDriverAvailableError):
        service.match_and_dispatch(trip.trip_id)
    assert service.get_trip(trip.trip_id).state == TripState.CANCELLED


def test_terminal_trip_cannot_advance():
    service = _service()
    trip = _request(service)
    service.cancel(trip.trip_id, "rider changed mind")
    assert trip.state == TripState.CANCELLED
    with pytest.raises(TripAlreadyTerminalError):
        service.advance(trip.trip_id, TripState.PICKUP)


def test_unknown_trip_raises():
    service = _service()
    with pytest.raises(TripNotFoundError):
        service.get_trip("trip-999999")


def test_reliability_report_counts_by_vertical():
    service = _service()
    t1 = _request(service)
    service.match_and_dispatch(t1.trip_id)
    service.advance(t1.trip_id, TripState.PICKUP)
    service.advance(t1.trip_id, TripState.IN_PROGRESS)
    service.advance(t1.trip_id, TripState.COMPLETED)
    t2 = _request(service)
    service.cancel(t2.trip_id, "rider cancelled")
    report = service.reliability_report()
    assert report["rider"] == {"completed": 1, "cancelled": 1, "active": 0}


def test_event_log_dedupes_and_resumes():
    log = EventLog()
    e1 = log.append("trip-1", "ev-1", "trip.requested")
    assert log.append("trip-1", "ev-1", "trip.requested") is None
    log.append("trip-1", "ev-2", "trip.matched")
    assert len(log) == 2
    resumed = log.events_for("trip-1", after_seq=1)
    assert [e.event_id for e in resumed] == ["ev-2"]
    assert e1.seq == 1
