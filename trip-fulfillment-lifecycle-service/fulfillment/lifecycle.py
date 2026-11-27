"""Trip lifecycle state machine.

Phases modelled on the Fulfillment Platform flow: shopping, ordering,
matching & dispatching, and tracking. A trip moves through one ordered
lifecycle; every transition is validated so an illegal jump (e.g. a
completed trip going back to dispatch) is rejected instead of silently
applied. Terminal states are COMPLETED and CANCELLED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TripState(str, Enum):
    REQUESTED = "requested"          # order placed, shopping/ordering done
    SEARCHING = "searching"          # looking for a driver (matching)
    MATCHED = "matched"              # driver assigned, not yet dispatched
    DISPATCHED = "dispatched"        # driver en route to pickup
    PICKUP = "pickup"                # driver arrived, rider boarding
    IN_PROGRESS = "in_progress"      # trip underway (tracking phase)
    COMPLETED = "completed"          # terminal
    CANCELLED = "cancelled"          # terminal


# Allowed forward transitions. CANCELLED is reachable from every
# non-terminal state; COMPLETED only from IN_PROGRESS.
TRANSITIONS: dict[TripState, set[TripState]] = {
    TripState.REQUESTED: {TripState.SEARCHING, TripState.CANCELLED},
    TripState.SEARCHING: {TripState.MATCHED, TripState.CANCELLED},
    TripState.MATCHED: {TripState.DISPATCHED, TripState.CANCELLED},
    TripState.DISPATCHED: {TripState.PICKUP, TripState.CANCELLED},
    TripState.PICKUP: {TripState.IN_PROGRESS, TripState.CANCELLED},
    TripState.IN_PROGRESS: {TripState.COMPLETED, TripState.CANCELLED},
    TripState.COMPLETED: set(),
    TripState.CANCELLED: set(),
}

TERMINAL = {TripState.COMPLETED, TripState.CANCELLED}


class IllegalTransitionError(ValueError):
    """Raised when a lifecycle transition is not in TRANSITIONS."""


def transition(trip: "Trip", new_state: TripState) -> "Trip":
    """Move a trip to ``new_state`` if the transition is legal.

    Mutates the trip in place (records the step in its history) and
    returns it, so callers can chain calls. Raises
    IllegalTransitionError on an illegal jump.
    """
    if new_state not in TRANSITIONS[trip.state]:
        raise IllegalTransitionError(
            f"cannot move trip {trip.trip_id} from {trip.state.value} "
            f"to {new_state.value}"
        )
    trip.state = new_state
    trip.history.append(new_state)
    return trip


@dataclass
class Trip:
    trip_id: str
    rider_id: str
    vertical: str  # e.g. "rider", "eats", "grocery", "package"
    pickup_lat: float
    pickup_lon: float
    dropoff_lat: float
    dropoff_lon: float
    state: TripState = TripState.REQUESTED
    driver_id: str | None = None
    fare_cents: int | None = None
    history: list[TripState] = field(default_factory=lambda: [TripState.REQUESTED])

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL
