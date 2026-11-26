"""Plain-language Safety Intelligence briefing (text + JSON summary)."""

from __future__ import annotations

import json

from .anomaly import find_anomalies
from .data import CATEGORIES
from .risk import likelihood_band, risk_matrix_cell, risk_scores
from .trends import emerging_risks, monthly_rates


def build_briefing(
    counts: dict[str, dict[str, int]],
    exposure: list,
) -> dict[str, object]:
    """Run the full pipeline and return the structured briefing."""
    rates = monthly_rates(counts, exposure)
    risks = risk_scores(rates)
    emerging = emerging_risks(rates)
    anomalies = find_anomalies(rates)
    latest_month = sorted(rates)[-1]
    matrix = {
        category: risk_matrix_cell(
            likelihood_band(rates[latest_month][category]),
            _severity_weight(category),
        )
        for category in CATEGORIES
    }
    return {
        "latest_month": latest_month,
        "risk_ranking": risks,
        "emerging_risks": emerging,
        "anomalies": anomalies,
        "risk_matrix_latest_month": matrix,
    }


def _severity_weight(category: str) -> int:
    from .data import SEVERITY_WEIGHTS

    return SEVERITY_WEIGHTS[category]


def render_briefing_text(briefing: dict[str, object]) -> str:
    """Plain-language briefing a non-technical safety leader can act on."""
    lines = [
        "SAFETY INTELLIGENCE BRIEFING",
        f"Latest month in data: {briefing['latest_month']}",
        "",
        "Top risks (severity-weighted, most recent 6 months):",
    ]
    for rank, row in enumerate(briefing["risk_ranking"], start=1):  # type: ignore[union-attr]
        lines.append(
            f"{rank}. {row['category']}: score {row['score']} "
            f"(rate {row['recent_rate']} per 10k flights, "
            f"severity weight {row['severity_weight']}, trend {row['trend']})"
        )
    lines.append("")
    lines.append("Emerging risks (recent rate well above baseline and rising):")
    emerging = briefing["emerging_risks"]  # type: ignore[assignment]
    if not emerging:
        lines.append("None flagged this month.")
    for row in emerging:  # type: ignore[union-attr]
        lines.append(
            f"- {row['category']}: latest rate {row['recent_rate']} vs "
            f"baseline {row['baseline_rate']} per 10k flights "
            f"(z = {row['max_recent_z']}, rising {row['slope_per_month']}/month). "
            "Recommend a focused review of recent reports in this category."
        )
    lines.append("")
    lines.append("Anomalous months (rate above the IQR upper fence):")
    anomalies = briefing["anomalies"]  # type: ignore[assignment]
    if not anomalies:
        lines.append("None flagged.")
    for row in anomalies:  # type: ignore[union-attr]
        lines.append(
            f"- {row['month']} {row['category']}: rate {row['rate']} "
            f"above fence {row['upper_fence']} (z = {row['z']})."
        )
    lines.append("")
    lines.append("Risk matrix, latest month (likelihood x severity):")
    for category, cell in briefing["risk_matrix_latest_month"].items():  # type: ignore[union-attr]
        lines.append(f"- {category}: {cell}")
    lines.append("")
    lines.append(
        "Note: synthetic demo data. Rates are per 10,000 flights; "
        "baselines are the first 12 months of the series."
    )
    return "\n".join(lines)


def render_briefing_json(briefing: dict[str, object]) -> str:
    """Machine-readable briefing for dashboards and downstream tools."""
    return json.dumps(briefing, indent=2, sort_keys=True)
