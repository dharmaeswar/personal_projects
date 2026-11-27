"""Driver matching: score nearby drivers, pick the best one.

Matching is a deterministic scoring problem, not first-come-first-served:
ETA to the pickup dominates, with small bonuses for higher-rated drivers
and a penalty for drivers already on a consecutive-trip streak, so work
spreads across the fleet instead of piling onto the same driver. Only
online drivers within the search radius are eligible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0
DEFAULT_RADIUS_KM = 10.0


@dataclass(frozen=True)
class Driver:
    driver_id: str
    lat: float
    lon: float
    rating: float  # 0.0 - 5.0
    online: bool = True
    consecutive_trips: int = 0
    vehicle_seats: int = 4


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def score_driver(driver: Driver, pickup_lat: float, pickup_lon: float,
                 avg_speed_kmh: float = 30.0) -> float:
    """Lower is better. ETA minutes dominate; rating and streak adjust it.

    ETA minutes + (5 - rating) * 2 minutes - streak penalty capped so a
    long streak never outweighs a much closer driver.
    """
    distance = haversine_km(driver.lat, driver.lon, pickup_lat, pickup_lon)
    eta_min = distance / avg_speed_kmh * 60.0
    rating_adjust = (5.0 - driver.rating) * 2.0
    streak_penalty = min(driver.consecutive_trips, 5) * 0.5
    return eta_min + rating_adjust + streak_penalty


def match_driver(drivers: list[Driver], pickup_lat: float, pickup_lon: float,
                 *, radius_km: float = DEFAULT_RADIUS_KM,
                 min_seats: int = 1) -> Driver | None:
    """Return the best eligible driver, or None when nobody qualifies."""
    eligible = [
        d for d in drivers
        if d.online
        and d.vehicle_seats >= min_seats
        and haversine_km(d.lat, d.lon, pickup_lat, pickup_lon) <= radius_km
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda d: score_driver(d, pickup_lat, pickup_lon))
