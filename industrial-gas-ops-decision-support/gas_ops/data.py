"""Seeded synthetic data for industrial-gas production and distribution.

All plants, customers, locations and demand are synthetic and seeded:
nothing here describes a real Linde plant, customer, contract or delivery.
Coordinates are kilometres on a flat local grid around Tonawanda, NY.
Products are the standard industrial gases: oxygen, nitrogen, argon,
hydrogen.
"""

import math
import random

# (plant_id, name, product, daily capacity in tonnes, x_km, y_km)
PLANTS = [
    ("P-01", "Tonawanda Air Separation", "oxygen", 420.0, 0.0, 0.0),
    ("P-02", "Tonawanda Nitrogen", "nitrogen", 380.0, 4.0, 2.0),
    ("P-03", "Buffalo Argon", "argon", 95.0, 9.0, -6.0),
    ("P-04", "Niagara Hydrogen", "hydrogen", 60.0, -14.0, 11.0),
    ("P-05", "Rochester Oxygen", "oxygen", 260.0, 52.0, 18.0),
]

# (customer_id, name, product, base daily demand in tonnes, x_km, y_km)
CUSTOMERS = [
    ("C-01", "Lakeshore Steel Mill", "oxygen", 96.0, 12.0, 5.0),
    ("C-02", "Niagara Chemical Works", "oxygen", 74.0, -9.0, 14.0),
    ("C-03", "Erie County Hospital", "oxygen", 18.0, 16.0, -3.0),
    ("C-04", "Buffalo Food Freezing", "nitrogen", 88.0, 7.0, -9.0),
    ("C-05", "Ontario Electronics Fab", "nitrogen", 63.0, -22.0, 20.0),
    ("C-06", "Rochester Pharma Plant", "nitrogen", 41.0, 47.0, 22.0),
    ("C-07", "Tonawanda Welding Supply", "argon", 22.0, 3.0, 4.0),
    ("C-08", "Syracuse Metalworks", "argon", 31.0, 68.0, 30.0),
    ("C-09", "Albany Fuel Cell Depot", "hydrogen", 14.0, 88.0, 41.0),
    ("C-10", "Buffalo Glassworks", "oxygen", 52.0, 10.0, -12.0),
    ("C-11", "Jamestown Fabrication", "nitrogen", 27.0, -38.0, -25.0),
    ("C-12", "Lockport Chemical", "oxygen", 44.0, 19.0, 9.0),
]

DAYS = 90


def generate_demand_history(seed=7):
    """Return {customer_id: [daily demand in tonnes for DAYS days]}.

    Demand = base * (1 + trend) * weekly seasonality + Gaussian noise,
    clipped at zero. The seed makes every run reproducible.
    """
    rng = random.Random(seed)
    history = {}
    for cust_id, _name, _product, base, _x, _y in CUSTOMERS:
        trend = rng.uniform(0.0004, 0.0016)  # slow daily growth
        weekly_amp = rng.uniform(0.06, 0.14)
        noise_sd = base * rng.uniform(0.05, 0.09)
        series = []
        for day in range(DAYS):
            seasonal = 1.0 + weekly_amp * math.sin(2 * math.pi * day / 7.0)
            level = base * (1.0 + trend * day) * seasonal
            value = max(0.0, rng.gauss(level, noise_sd))
            series.append(round(value, 2))
        history[cust_id] = series
    return history


def plant_by_id(plant_id):
    for plant in PLANTS:
        if plant[0] == plant_id:
            return plant
    raise KeyError(f"unknown plant {plant_id}")


def customer_by_id(customer_id):
    for cust in CUSTOMERS:
        if cust[0] == customer_id:
            return cust
    raise KeyError(f"unknown customer {customer_id}")
