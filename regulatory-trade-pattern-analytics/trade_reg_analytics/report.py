"""Regulatory reporting: Markdown summary, CSV exports and charts.

Produces the artefacts a market-regulation analyst would hand to a
reviewer: a Markdown report with findings and method notes, CSV files
for the findings and daily volumes, and a small standalone SVG bar
chart of findings by pattern (pure Python, no charting dependency).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def findings_summary(findings: pd.DataFrame) -> dict:
    """Counts and top severity per pattern, JSON-serialisable."""
    if findings.empty:
        return {"total_findings": 0, "by_pattern": {}, "top_severity": 0}
    by_pattern = (
        findings.groupby("pattern")
        .agg(count=("pattern", "size"), max_severity=("severity", "max"))
        .reset_index()
        .to_dict("records")
    )
    return {
        "total_findings": int(len(findings)),
        "by_pattern": {r["pattern"]: {"count": int(r["count"]), "max_severity": int(r["max_severity"])} for r in by_pattern},
        "top_severity": int(findings["severity"].max()),
    }


def write_report(
    findings: pd.DataFrame,
    daily: pd.DataFrame,
    out_dir: str | Path,
    title: str = "Regulatory Trade-Pattern Review",
) -> dict[str, str]:
    """Write report.md, findings.csv, daily_volume.csv, summary.json
    and findings_chart.svg into out_dir. Returns the file paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = findings_summary(findings)

    lines = [
        f"# {title}",
        "",
        f"Total findings: **{summary['total_findings']}**",
        f"Top severity: **{summary['top_severity']}**",
        "",
        "## Findings by pattern",
        "",
    ]
    if findings.empty:
        lines.append("No patterns flagged in this run.")
    else:
        for pattern, info in summary["by_pattern"].items():
            lines.append(f"- **{pattern}**: {info['count']} findings, max severity {info['max_severity']}")
        lines += ["", "## Findings detail", ""]
        for _, r in findings.iterrows():
            lines.append(
                f"- [{r['pattern']}] {r['instrument']} {r['trade_date']} "
                f"(severity {r['severity']}): {r['reason']}"
            )
    lines += [
        "",
        "## Method",
        "",
        "Rule-based detectors over a SQLite order/trade/position warehouse: "
        "wash trades (matched buy/sell, same account/day), spoofing "
        "(large orders cancelled within 10s), marking the close (late "
        "trades away from VWAP), and position concentration (>= 35% of "
        "net open interest). Synthetic seeded data; no real market data.",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    findings.to_csv(out / "findings.csv", index=False)
    daily.to_csv(out / "daily_volume.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_chart(summary["by_pattern"], out / "findings_chart.svg")
    return {
        "report": str(out / "report.md"),
        "findings": str(out / "findings.csv"),
        "daily_volume": str(out / "daily_volume.csv"),
        "summary": str(out / "summary.json"),
        "chart": str(out / "findings_chart.svg"),
    }


def _write_chart(by_pattern: dict, path: Path) -> None:
    """Simple horizontal bar chart of finding counts per pattern."""
    width, bar_h, gap = 520, 26, 10
    items = sorted(by_pattern.items(), key=lambda kv: -kv[1]["count"])
    height = max(60, 40 + len(items) * (bar_h + gap))
    max_count = max((v["count"] for v in by_pattern.values()), default=1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="10" y="22" font-family="sans-serif" font-size="14" font-weight="bold">'
        "Findings by pattern</text>",
    ]
    y = 40
    for name, info in items:
        bar_w = int(300 * info["count"] / max_count)
        parts.append(
            f'<text x="10" y="{y + 17}" font-family="sans-serif" font-size="12">{name}</text>'
        )
        parts.append(
            f'<rect x="190" y="{y}" width="{bar_w}" height="{bar_h}" fill="#1f4e79"/>'
        )
        parts.append(
            f'<text x="{200 + bar_w}" y="{y + 17}" font-family="sans-serif" font-size="12">'
            f"{info['count']}</text>"
        )
        y += bar_h + gap
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
