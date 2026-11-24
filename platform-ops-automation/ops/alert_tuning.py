"""Alert-threshold tuning for the Platform Ops Automation demo project.

Added for a Site Reliability Engineer application (NationsBenefits):
the posting asks for managing and optimizing alerting thresholds so real
incidents are detected while false positives are reduced. This module
replays a per-minute metric series (for example the 5xx error rate from
``ops/log_analysis.py``) against candidate thresholds, scores each one
against labelled incident windows, and recommends the threshold that
detects every incident with the fewest false-positive alerts.

All data is synthetic. No real monitoring system (Datadog or otherwise)
is contacted, and no production alerting experience is claimed.
"""

import random


def evaluate_threshold(samples, threshold, min_consecutive=1):
    """Score one threshold against a labelled per-minute series.

    ``samples`` is a list of dicts ``{"minute": int, "value": float,
    "incident": bool}`` in time order. An alert fires once, on the minute
    where ``value`` has stayed at or above ``threshold`` for
    ``min_consecutive`` consecutive minutes. An alert counts as a true
    positive when that minute is an incident minute, otherwise as a
    false positive. An incident run counts as detected when at least one
    alert fires on one of its minutes.
    """
    alerts = 0
    true_positives = 0
    false_positives = 0
    run = 0
    incidents_total = 0
    incidents_detected = 0
    in_incident = False
    run_detected = False
    for sample in samples:
        run = run + 1 if sample["value"] >= threshold else 0
        fired = run == min_consecutive
        if sample["incident"] and not in_incident:
            incidents_total += 1
            run_detected = False
            in_incident = True
        if fired:
            alerts += 1
            if sample["incident"]:
                true_positives += 1
                run_detected = True
            else:
                false_positives += 1
        if in_incident and not sample["incident"]:
            if run_detected:
                incidents_detected += 1
            in_incident = False
    if in_incident and run_detected:
        incidents_detected += 1
    return {
        "threshold": threshold,
        "min_consecutive": min_consecutive,
        "alerts": alerts,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_positive_share": false_positives / alerts if alerts else 0.0,
        "incidents_total": incidents_total,
        "incidents_detected": incidents_detected,
        "incidents_missed": incidents_total - incidents_detected,
    }


def sweep_thresholds(samples, candidates, min_consecutive=1):
    """Evaluate every candidate threshold; returns a list of results."""
    return [
        evaluate_threshold(samples, candidate, min_consecutive)
        for candidate in candidates
    ]


def recommend_threshold(samples, candidates, min_consecutive=1):
    """Pick the best candidate threshold for the labelled series.

    Preference order: miss no incident; then fewest false positives;
    then the lowest threshold (earliest warning). Returns the winning
    evaluation dict plus a plain-language ``reason``.
    """
    results = sweep_thresholds(samples, candidates, min_consecutive)
    if not results:
        raise ValueError("at least one candidate threshold is required")

    def sort_key(result):
        return (
            result["incidents_missed"],
            result["false_positives"],
            result["threshold"],
        )

    best = dict(min(results, key=sort_key))
    if best["incidents_missed"] == 0 and best["false_positives"] == 0:
        best["reason"] = "detects every incident with no false-positive alerts"
    elif best["incidents_missed"] == 0:
        best["reason"] = (
            "detects every incident with the fewest false-positive "
            "alerts (%d)" % best["false_positives"]
        )
    else:
        best["reason"] = (
            "no candidate detects every incident; this one misses the "
            "fewest (%d) with %d false positives"
            % (best["incidents_missed"], best["false_positives"])
        )
    return best


def generate_synthetic_series(seed=7, minutes=240):
    """Deterministic synthetic per-minute error-rate series.

    Baseline noise sits near 0.5-3%, two incident windows push the rate
    to 18-30%, and a few one-minute spikes reach 6-9% as false-positive
    bait for thresholds that are set too low.
    """
    rng = random.Random(seed)
    incident_windows = [(60, 74), (170, 179)]
    spike_minutes = {30, 120, 210}
    samples = []
    for minute in range(minutes):
        incident = any(start <= minute <= end for start, end in incident_windows)
        if incident:
            value = rng.uniform(0.18, 0.30)
        elif minute in spike_minutes:
            value = rng.uniform(0.06, 0.09)
        else:
            value = rng.uniform(0.005, 0.03)
        samples.append(
            {"minute": minute, "value": round(value, 4), "incident": incident}
        )
    return samples


if __name__ == "__main__":
    series = generate_synthetic_series()
    candidates = [0.04, 0.05, 0.08, 0.10, 0.15, 0.20]
    for result in sweep_thresholds(series, candidates, min_consecutive=2):
        print(result)
    print(recommend_threshold(series, candidates, min_consecutive=2))
