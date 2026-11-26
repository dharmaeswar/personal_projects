"""Tests for the industrial gas operations decision-support project."""

import json
import statistics
import urllib.request

import pytest

from gas_ops.api import make_server
from gas_ops.data import CUSTOMERS, PLANTS, generate_demand_history
from gas_ops.forecast import backtest, forecast
from gas_ops.optimize import assign_to_plants, distance, plan_route, tour_distance
from gas_ops.simulate import safety_stock, simulate_demand
from gas_ops.store import (
    explain_history_lookup,
    get_customer_history,
    get_inventory,
    init_db,
    list_deliveries,
    record_delivery,
    seed,
)


@pytest.fixture()
def seeded_conn():
    conn = init_db()
    seed(conn, PLANTS, CUSTOMERS, generate_demand_history())
    return conn


def test_data_is_deterministic_and_complete():
    first = generate_demand_history()
    second = generate_demand_history()
    assert first == second
    assert len(first) == len(CUSTOMERS) == 12
    assert all(len(series) == 90 for series in first.values())
    assert all(v >= 0 for series in first.values() for v in series)


def test_store_round_trip_and_index_use(seeded_conn):
    history = get_customer_history(seeded_conn, "C-01")
    assert len(history) == 90
    assert history == generate_demand_history()["C-01"]
    plan = explain_history_lookup(seeded_conn, "C-01")
    assert "USING INDEX" in plan or "USING COVERING INDEX" in plan
    inventory = get_inventory(seeded_conn)
    assert len(inventory) == 5
    assert all(row["on_hand_t"] > row["safety_stock_t"] for row in inventory)


def test_deliveries_recorded_and_listed(seeded_conn):
    delivery_id = record_delivery(seeded_conn, "P-01", "C-01", 96.0, 13.0, 0)
    rows = list_deliveries(seeded_conn, plant_id="P-01")
    assert len(rows) == 1
    assert rows[0]["delivery_id"] == delivery_id
    assert rows[0]["tonnes"] == 96.0


def test_forecast_beats_naive_on_average():
    history = generate_demand_history()
    mapes, naive_mapes = [], []
    for series in history.values():
        mape, naive = backtest(series)
        mapes.append(mape)
        naive_mapes.append(naive)
    assert statistics.fmean(mapes) < statistics.fmean(naive_mapes)
    assert statistics.fmean(mapes) < 20.0  # forecasts stay usable
    preds = forecast(history["C-01"], days=7)
    assert len(preds) == 7 and all(p >= 0 for p in preds)


def test_route_optimizer_beats_naive_order():
    plant_xy = (0.0, 0.0)
    points = [(c[4], c[5]) for c in CUSTOMERS if c[2] == "oxygen"]
    order, dist_km, naive_km = plan_route(plant_xy, points)
    assert sorted(order) == list(range(len(points)))
    assert dist_km <= naive_km
    assert dist_km < naive_km  # optimizer must actually improve here
    assert dist_km > 0
    # Tour is closed: starts and ends at the plant.
    assert dist_km == tour_distance([plant_xy] + [points[i] for i in order] + [plant_xy])


def test_route_distance_is_symmetric():
    assert distance((0.0, 0.0), (3.0, 4.0)) == 5.0
    assert distance((3.0, 4.0), (0.0, 0.0)) == 5.0


def test_assignment_respects_capacity_and_product():
    plants = [(p[0], p[2], p[3], p[4], p[5]) for p in PLANTS]
    customers = [(c[0], c[2], c[4], c[5]) for c in CUSTOMERS]
    demand = {c[0]: c[3] for c in CUSTOMERS}
    assignment, used = assign_to_plants(plants, customers, demand)
    for cust_id, plant_id in assignment.items():
        if plant_id is not None:
            plant = next(p for p in PLANTS if p[0] == plant_id)
            cust = next(c for c in CUSTOMERS if c[0] == cust_id)
            assert plant[2] == cust[2]  # product must match
    for plant in PLANTS:
        assert used[plant[0]] <= plant[3]  # never exceed daily capacity
    # The two oxygen plants near Tonawanda take most oxygen demand.
    assert assignment["C-01"] in ("P-01", "P-05")


def test_simulation_bounds_and_safety_stock():
    series = generate_demand_history()["C-01"]
    prob, mean, sd = simulate_demand(series, inventory_t=90.0)
    assert 0.0 <= prob <= 1.0
    assert mean > 0 and sd > 0
    # A huge inventory must be (near-)never stocked out; zero never safe.
    prob_huge, _, _ = simulate_demand(series, inventory_t=10000.0)
    prob_zero, _, _ = simulate_demand(series, inventory_t=0.0)
    assert prob_huge == 0.0
    assert prob_zero == 1.0
    assert safety_stock(series, service_level=0.99) > safety_stock(series, service_level=0.90)
    assert safety_stock(series) > 0


@pytest.fixture()
def live_server():
    server = make_server(port=0)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path) as resp:
        return json.loads(resp.read())


def test_api_endpoints(live_server):
    assert _get(live_server, "/health") == {"status": "ok"}
    dash = _get(live_server, "/api/dashboard")
    assert len(dash["plants"]) == 5
    assert len(dash["customers"]) == 12
    assert len(dash["inventory"]) == 5
    fc = _get(live_server, "/api/forecast?customer=C-01&days=7")
    assert len(fc["forecast"]) == 7
    assert fc["backtest_mape_pct"] < fc["naive_mape_pct"]
    sim = _get(live_server, "/api/simulate?customer=C-01&inventory=90")
    assert 0.0 <= sim["stockout_probability"] <= 1.0
    assert sim["safety_stock_95_t"] > 0


def test_api_route_plans_and_persists(live_server):
    req = urllib.request.Request(
        live_server + "/api/route",
        data=json.dumps(
            {"plant": "P-01", "customers": ["C-01", "C-03", "C-10", "C-12"]}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    assert sorted(result["order"]) == ["C-01", "C-03", "C-10", "C-12"]
    assert result["distance_km"] <= result["naive_km"]
    assert result["saved_pct"] >= 0
    dash = _get(live_server, "/api/dashboard")
    assert len(dash["deliveries"]) == 4


def test_api_rejects_wrong_product(live_server):
    req = urllib.request.Request(
        live_server + "/api/route",
        data=json.dumps({"plant": "P-01", "customers": ["C-04"]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req)
    assert excinfo.value.code == 400
