"""Run the home-health episode pipeline and write a report.

Usage: python run_home_health.py
Writes home_health_report.txt in the project root.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.home_health import (
    build_episode_summary,
    generate_home_health,
    quarantine_visits,
    validate_episodes,
    validate_visits,
)


def main() -> None:
    data = generate_home_health()
    episodes, visits = data["episodes"], data["visits"]
    ep_results = validate_episodes(episodes)
    visit_results = validate_visits(visits, episodes)
    silver, quarantine = quarantine_visits(visits, episodes)
    summary = build_episode_summary(silver, episodes)

    lines = [
        "HOME-HEALTH EPISODE PIPELINE REPORT",
        f"Episodes: {len(episodes)}; visits (bronze): {len(visits)}",
        "",
        "Episode checks:",
    ]
    for r in ep_results:
        lines.append(f"  {r}")
    lines.append("")
    lines.append("Visit checks:")
    for r in visit_results:
        lines.append(f"  {r}")
    lines += [
        "",
        f"Silver visits: {len(silver)}; quarantined: {len(quarantine)}",
        f"Gold episode summary rows: {len(summary)}",
        f"Total silver minutes: {int(silver['duration_minutes'].sum())}; "
        f"gold total minutes: {int(summary['total_minutes'].sum())}",
        "Reconciliation: "
        + ("PASS" if int(summary["total_minutes"].sum())
           == int(silver["duration_minutes"].sum()) else "FAIL"),
    ]
    report = "\n".join(lines) + "\n"
    Path("home_health_report.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
