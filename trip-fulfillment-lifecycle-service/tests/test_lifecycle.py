import pytest

from fulfillment.lifecycle import (
    IllegalTransitionError,
    Trip,
    TripState,
    transition,
)


def _trip():
    return Trip("trip-000001", "rider-1", "rider", 37.7, -122.4, 37.8, -122.5)


def test_full_happy_path_lifecycle():
    trip = _trip()
    for state in (TripState.SEARCHING, TripState.MATCHED, TripState.DISPATCHED,
                  TripState.PICKUP, TripState.IN_PROGRESS, TripState.COMPLETED):
        transition(trip, state)
    assert trip.state == TripState.COMPLETED
    assert trip.is_terminal
    assert [s.value for s in trip.history] == [
        "requested", "searching", "matched", "dispatched",
        "pickup", "in_progress", "completed",
    ]


def test_illegal_jump_rejected():
    trip = _trip()
    with pytest.raises(IllegalTransitionError):
        transition(trip, TripState.COMPLETED)
    assert trip.state == TripState.REQUESTED


def test_skip_a_phase_rejected():
    trip = _trip()
    transition(trip, TripState.SEARCHING)
    with pytest.raises(IllegalTransitionError):
        transition(trip, TripState.DISPATCHED)


def test_cancel_from_any_live_state():
    for start in (TripState.REQUESTED, TripState.SEARCHING, TripState.MATCHED,
                  TripState.DISPATCHED, TripState.PICKUP, TripState.IN_PROGRESS):
        trip = _trip()
        trip.state = start
        transition(trip, TripState.CANCELLED)
        assert trip.is_terminal


def test_terminal_states_accept_no_transitions():
    trip = _trip()
    transition(trip, TripState.CANCELLED)
    with pytest.raises(IllegalTransitionError):
        transition(trip, TripState.REQUESTED)
