"""Monte Carlo demand simulation for inventory decisions.

Given a customer's demand history, simulate next-day demand many times
with a Normal(mean, sd) fitted to that history (seeded, reproducible).
The outputs are the stockout probability at a given on-hand inventory and
the safety stock needed for a target service level. The Normal assumption
is stated in the README as a limitation: real demand is skewed and has
occasional spikes this model does not reproduce.
"""

import math
import random
import statistics


def simulate_demand(series, inventory_t, trials=2000, seed=11):
    """Return (stockout probability 0-1, mean demand, sd of demand).

    A stockout is a simulated demand above the on-hand inventory.
    """
    mean = statistics.fmean(series)
    sd = statistics.pstdev(series) if len(series) > 1 else 0.0
    rng = random.Random(seed)
    stockouts = 0
    for _ in range(trials):
        draw = rng.gauss(mean, sd)
        if draw > inventory_t:
            stockouts += 1
    return round(stockouts / trials, 4), round(mean, 2), round(sd, 2)


def safety_stock(series, service_level=0.95, lead_days=1):
    """Safety stock for a target service level, Normal-demand formula.

    Uses the standard z-value for the service level times the standard
    deviation of demand over the lead time. z for 95% is 1.645.
    """
    z_values = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z = z_values.get(service_level, 1.645)
    sd = statistics.pstdev(series) if len(series) > 1 else 0.0
    return round(z * sd * math.sqrt(lead_days), 2)
