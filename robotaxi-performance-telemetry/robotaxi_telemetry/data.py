"""Synthetic robotaxi fleet telemetry generator.

All data is synthetic and seeded. It models the kind of trip-level
telemetry a robotaxi performance team would analyse: miles driven,
interventions by type, mission outcomes, recovery times, remote
assistance, and vehicle availability across software releases.
No real vehicles, trips, or operators are involved.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

INTERVENTION_TYPES = (
    "safety_critical",
    "unnecessary_stop",
    "stuck_scenario",
    "manoeuvre_execution",
)
ROAD_TYPES = ("urban", "suburban", "highway")
RELEASES = ("2026.09", "2026.10", "2026.11")


@dataclass
class Trip:
    trip_id: str
    vehicle_id: str
    release: str
    road_type: str
    miles: float
    duration_min: float
    mission_completed: bool
    interventions: dict = field(default_factory=dict)
    recovery_min: float = 0.0
    remote_assistance: bool = False
    pickup_delay_min: float = 0.0


def _interventions(rng: random.Random, release: str, road: str) -> dict:
    # Later releases intervene less often; urban roads intervene most.
    base = {"2026.09": 0.055, "2026.10": 0.042, "2026.11": 0.030}[release]
    road_mult = {"urban": 1.6, "suburban": 1.0, "highway": 0.7}[road]
    out = {}
    for kind in INTERVENTION_TYPES:
        kind_mult = {
            "safety_critical": 0.25,
            "unnecessary_stop": 1.0,
            "stuck_scenario": 0.55,
            "manoeuvre_execution": 0.8,
        }[kind]
        lam = base * road_mult * kind_mult
        n = 0
        # Poisson draw via Knuth's algorithm (small lambda, fine here).
        limit = 2.718281828459045 ** (-lam)
        p = 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                break
            n += 1
        out[kind] = n
    return out


def generate_trips(n_trips: int = 1200, seed: int = 42) -> list[Trip]:
    rng = random.Random(seed)
    trips: list[Trip] = []
    for i in range(n_trips):
        release = rng.choice(RELEASES)
        road = rng.choice(ROAD_TYPES)
        miles = round(rng.uniform(2.0, 28.0), 2)
        duration = round(miles / rng.uniform(14.0, 32.0) * 60.0, 1)
        interventions = _interventions(rng, release, road)
        total = sum(interventions.values())
        completed = rng.random() > (0.02 + 0.10 * min(total, 3))
        recovery = round(rng.uniform(2.0, 25.0), 1) if total > 0 else 0.0
        trips.append(
            Trip(
                trip_id=f"T{i:05d}",
                vehicle_id=f"V{rng.randint(1, 40):03d}",
                release=release,
                road_type=road,
                miles=miles,
                duration_min=duration,
                mission_completed=completed,
                interventions=interventions,
                recovery_min=recovery,
                remote_assistance=rng.random() < (0.05 + 0.12 * min(total, 2)),
                pickup_delay_min=round(rng.uniform(0.0, 6.0), 1),
            )
        )
    return trips


def to_rows(trips: list[Trip]) -> list[dict]:
    """Flatten trips to one row per trip, ready for SQL-style analysis."""
    rows = []
    for t in trips:
        row = {
            "trip_id": t.trip_id,
            "vehicle_id": t.vehicle_id,
            "release": t.release,
            "road_type": t.road_type,
            "miles": t.miles,
            "duration_min": t.duration_min,
            "mission_completed": int(t.mission_completed),
            "recovery_min": t.recovery_min,
            "remote_assistance": int(t.remote_assistance),
            "pickup_delay_min": t.pickup_delay_min,
        }
        for kind in INTERVENTION_TYPES:
            row[f"interventions_{kind}"] = t.interventions[kind]
        row["interventions_total"] = sum(t.interventions.values())
        rows.append(row)
    return rows
