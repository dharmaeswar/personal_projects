# Robotaxi Performance & Capability — Readiness Report (synthetic data)

## Overall KPIs

- trips: 1200
- miles: 18088.2
- interventions_per_1k_miles: 6.8
- by_type_per_1k_miles: {'safety_critical': 0.442, 'unnecessary_stop': 3.096, 'stuck_scenario': 1.106, 'manoeuvre_execution': 2.156}
- mission_completion_rate: 0.9717
- mean_recovery_min: 14.29
- remote_assistance_rate: 0.06
- mean_pickup_delay_min: 3.0
- availability_proxy: 0.9008
- interventions_per_1k_miles_ci95: [5.651, 8.113]

## KPIs by software release

- 2026.09: 409 trips, 6335.2 miles, 8.682 interventions/1k miles, mission completion 0.9682, mean recovery 15.2 min
- 2026.10: 395 trips, 5784.6 miles, 6.396 interventions/1k miles, mission completion 0.9722, mean recovery 13.45 min
- 2026.11: 396 trips, 5968.4 miles, 5.194 interventions/1k miles, mission completion 0.9747, mean recovery 13.74 min

## KPIs by road type

- highway: 4.354 interventions/1k miles, mission completion 0.9716
- suburban: 7.041 interventions/1k miles, mission completion 0.9794
- urban: 9.152 interventions/1k miles, mission completion 0.9639

## Release-over-release rate comparison (Poisson, two-sided)

- 2026.09_vs_2026.10: rate ratio 0.737, p-value 0.1746 — not significant — treat as noise
- 2026.10_vs_2026.11: rate ratio 0.812, p-value 0.399 — not significant — treat as noise

## Readiness read

Later releases show lower intervention rates and higher mission completion in this synthetic sample; the Poisson comparisons say which of those moves clear the 95% bar and which are noise. Safety-critical interventions are the rarest type and carry the widest relative uncertainty, so they need the most miles before a release claim is trusted.
