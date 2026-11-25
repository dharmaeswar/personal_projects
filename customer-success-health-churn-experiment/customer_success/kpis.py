"""KPI definitions: the Customer Success metrics the team manages to.

Each KPI has one definition, one owner-readable formula, and one computation
over the same synthetic customers, so a leadership review reads the same
number the pipeline produced — no hand-rebuilt slides.
"""
import statistics

KPI_DEFINITIONS = {
    "time_to_value_days": "Median days from signup to first value (first invoice paid / books closed)",
    "adoption_rate": "Share of customers using >= 4 of 8 tracked features",
    "healthy_share": "Share of customers in the Healthy health band",
    "retention_rate": "Share of customers retained over the 12-month window",
    "expansion_rate": "Share of retained customers who expanded ARR",
    "tickets_per_customer": "Mean support tickets per customer in the last 90 days",
    "nps_mean": "Mean NPS (0-10) across customers",
}


def median_time_to_value(customers):
    return statistics.median(c["time_to_value_days"] for c in customers)


def adoption_rate(customers):
    return sum(1 for c in customers if c["features_adopted"] >= 4) / len(customers)


def retention_rate(customers):
    return sum(1 for c in customers if c["retained"]) / len(customers)


def expansion_rate(customers):
    retained = [c for c in customers if c["retained"]]
    return sum(1 for c in retained if c["expanded"]) / len(retained)


def compute_kpis(customers):
    return {
        "time_to_value_days": median_time_to_value(customers),
        "adoption_rate": round(adoption_rate(customers), 3),
        "retention_rate": round(retention_rate(customers), 3),
        "expansion_rate": round(expansion_rate(customers), 3),
        "tickets_per_customer": round(
            sum(c["tickets_90d"] for c in customers) / len(customers), 2
        ),
        "nps_mean": round(sum(c["nps"] for c in customers) / len(customers), 2),
        "n": len(customers),
    }
