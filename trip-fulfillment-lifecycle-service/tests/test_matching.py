from fulfillment.matching import Driver, haversine_km, match_driver, score_driver

PICKUP = (37.7749, -122.4194)


def _drivers():
    return [
        Driver("near", 37.7750, -122.4195, 4.9, consecutive_trips=0),
        Driver("far", 37.8249, -122.4194, 5.0, consecutive_trips=0),
        Driver("offline", 37.7749, -122.4194, 5.0, online=False),
        Driver("small-car", 37.7760, -122.4205, 4.5, vehicle_seats=1),
    ]


def test_haversine_same_point_is_zero():
    assert haversine_km(37.7749, -122.4194, 37.7749, -122.4194) == 0.0


def test_haversine_known_distance():
    # ~5.5 km straight north from the pickup point.
    assert abs(haversine_km(37.7749, -122.4194, 37.8249, -122.4194) - 5.56) < 0.05


def test_closest_driver_wins():
    assert match_driver(_drivers(), *PICKUP).driver_id == "near"


def test_offline_driver_never_matched():
    drivers = [Driver("off", 37.7749, -122.4194, 5.0, online=False)]
    assert match_driver(drivers, *PICKUP) is None


def test_no_driver_in_radius_returns_none():
    drivers = [Driver("far-away", 38.5, -122.0, 5.0)]
    assert match_driver(drivers, *PICKUP) is None


def test_seat_requirement_filters():
    drivers = [Driver("two-seater", 37.7750, -122.4195, 5.0, vehicle_seats=2)]
    assert match_driver(drivers, *PICKUP, min_seats=4) is None
    assert match_driver(drivers, *PICKUP, min_seats=2).driver_id == "two-seater"


def test_higher_rating_beats_equal_distance():
    a = Driver("a", 37.7750, -122.4195, 4.0, consecutive_trips=0)
    b = Driver("b", 37.7750, -122.4195, 5.0, consecutive_trips=0)
    assert score_driver(b, *PICKUP) < score_driver(a, *PICKUP)
