"""Multi-touch attribution on synthetic journeys.

Four rules on the same journeys, so the comparison is apples-to-apples:
- last-touch: all credit to the final touch before conversion.
- first-touch: all credit to the first touch.
- position-based (40/20/40): first and last touch split 40% each, the middle
  shares the remaining 20%.
- Shapley: exact Shapley value over the channel set, where a coalition's
  value is its simulated conversion rate (channels outside the coalition
  cannot appear in the journey).

Credit is reported as a share of total converted journeys.
"""

from itertools import combinations

import numpy as np

from .data_gen import TOUCH_PROBS, subset_conversion_rate

ALL_CHANNELS = list(TOUCH_PROBS)


def _credit(journeys, rule):
    totals = {c: 0.0 for c in ALL_CHANNELS}
    converted = journeys[(journeys["converted"] == 1)
                         & (journeys["touches"].map(len) > 0)]
    for touches in converted["touches"]:
        if rule == "last_touch":
            totals[touches[-1]] += 1.0
        elif rule == "first_touch":
            totals[touches[0]] += 1.0
        elif rule == "position_based":
            if len(touches) == 1:
                totals[touches[0]] += 1.0
            elif len(touches) == 2:
                # No middle touch exists, so first and last split evenly.
                totals[touches[0]] += 0.5
                totals[touches[-1]] += 0.5
            else:
                totals[touches[0]] += 0.4
                totals[touches[-1]] += 0.4
                for mid in touches[1:-1]:
                    totals[mid] += 0.2 / max(1, len(touches) - 2)
    n = max(1, len(converted))
    return {c: round(v / n, 3) for c, v in totals.items()}


def shapley_credit(n_per_subset=4000, seed=99):
    """Exact Shapley values from simulated coalition conversion rates."""
    channels = ALL_CHANNELS
    value = {}
    for r in range(len(channels) + 1):
        for subset in combinations(channels, r):
            value[frozenset(subset)] = subset_conversion_rate(
                subset, n=n_per_subset, seed=seed)
    import math
    n = len(channels)
    shapley = {}
    for ch in channels:
        others = [c for c in channels if c != ch]
        total = 0.0
        for r in range(len(others) + 1):
            for subset in combinations(others, r):
                s = frozenset(subset)
                weight = (math.factorial(len(s))
                          * math.factorial(n - len(s) - 1)
                          / math.factorial(n))
                total += weight * (value[s | {ch}] - value[s])
        shapley[ch] = total
    total = sum(shapley.values())
    return {c: round(v / total, 3) for c, v in shapley.items()} if total else shapley


def compare_attribution(journeys, n_per_subset=4000):
    """Return one row per rule with each channel's share of conversions."""
    rules = ["last_touch", "first_touch", "position_based"]
    out = {rule: _credit(journeys, rule) for rule in rules}
    out["shapley"] = shapley_credit(n_per_subset=n_per_subset)
    return out
