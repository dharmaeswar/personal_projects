"""Delivery-route optimization and plant assignment.

Routes are planned on the flat kilometre grid: Euclidean distance between
stops. The optimizer builds a nearest-neighbour tour from the plant and
then improves it with 2-opt swaps until no swap shortens the tour, so the
result is always at least as good as the greedy tour. Plant assignment is
a greedy capacity check: each customer's next-day demand goes to the
nearest plant making the same product that still has free capacity.
"""

import math


def distance(a, b):
    return round(math.hypot(a[0] - b[0], a[1] - b[1]), 2)


def tour_distance(stops):
    """Total distance of a tour given as a list of (x, y) points."""
    return round(
        sum(distance(stops[i], stops[i + 1]) for i in range(len(stops) - 1)), 2
    )


def nearest_neighbour(start, points):
    """Greedy tour: repeatedly visit the nearest unvisited point."""
    remaining = list(points)
    tour = [start]
    current = start
    while remaining:
        nxt = min(remaining, key=lambda p: distance(current, p))
        tour.append(nxt)
        remaining.remove(nxt)
        current = nxt
    tour.append(start)  # return to the plant
    return tour


def two_opt(tour):
    """Improve a tour with 2-opt swaps until no swap shortens it."""
    best = list(tour)
    best_len = tour_distance(best)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                cand_len = tour_distance(candidate)
                if cand_len < best_len - 1e-9:
                    best, best_len = candidate, cand_len
                    improved = True
    return best, best_len


def plan_route(plant_xy, customer_xys):
    """Return (ordered customer indices, total km, naive-order km).

    The naive baseline visits customers in the order given, so the
    improvement over it is measurable.
    """
    if not customer_xys:
        return [], 0.0, 0.0
    naive = [plant_xy] + list(customer_xys) + [plant_xy]
    naive_len = tour_distance(naive)
    greedy = nearest_neighbour(plant_xy, list(customer_xys))
    best, best_len = two_opt(greedy)
    # Map the optimized tour back to customer indices (skip plant endpoints).
    order = []
    for point in best[1:-1]:
        order.append(customer_xys.index(point))
    return order, best_len, naive_len


def assign_to_plants(plants, customers, demand):
    """Assign each customer to the nearest same-product plant with capacity.

    `plants` is a list of (plant_id, product, capacity_t, x, y);
    `customers` a list of (customer_id, product, x, y);
    `demand` maps customer_id -> tonnes needed. Returns
    {customer_id: plant_id or None} plus {plant_id: used_t}.
    """
    remaining = {p[0]: p[2] for p in plants}
    used = {p[0]: 0.0 for p in plants}
    assignment = {}
    for cust_id, product, cx, cy in customers:
        need = demand.get(cust_id, 0.0)
        options = [
            p for p in plants
            if p[1] == product and remaining[p[0]] >= need
        ]
        if not options:
            assignment[cust_id] = None
            continue
        plant = min(options, key=lambda p: math.hypot(p[3] - cx, p[4] - cy))
        assignment[cust_id] = plant[0]
        remaining[plant[0]] -= need
        used[plant[0]] += need
    return assignment, used
