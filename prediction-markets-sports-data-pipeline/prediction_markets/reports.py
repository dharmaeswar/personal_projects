"""Packaged reports: the artefacts a researcher hands to traders.

``build_report`` produces one JSON report and one plain-text report:
data-quality summary (rows kept / quarantined), the biggest market
movers, the largest model-vs-market edges at the latest snapshot, and
the backtest result. Reports are deterministic for a given feed seed.
"""

from __future__ import annotations

import json

import pandas as pd

from .cleanse import CleanRecord, CleanseReport
from .ingest import EVENTS
from .signals import backtest, consensus, movements


def build_report(records: list[CleanRecord], cleanse_report: CleanseReport) -> dict:
    cons = consensus(records)
    movers = movements(cons)
    latest = cons.sort_values("ts").groupby("event_id").tail(1)
    model = {e[0]: e[3] for e in EVENTS}
    label = {e[0]: e[1] for e in EVENTS}
    edges = []
    for _, row in latest.iterrows():
        edges.append({
            "event_id": row["event_id"],
            "label": label[row["event_id"]],
            "model_home": model[row["event_id"]],
            "market_home": round(float(row["fair_home"]), 4),
            "edge_home": round(model[row["event_id"]] - float(row["fair_home"]), 4),
        })
    edges.sort(key=lambda e: abs(e["edge_home"]), reverse=True)
    bt = backtest(records)
    return {
        "data_quality": cleanse_report.as_dict() | {"quarantined": len(cleanse_report.quarantined)},
        "events": len(EVENTS),
        "top_movers": [
            {"event_id": m.event_id, "label": label[m.event_id],
             "move": round(m.move, 4), "max_step": round(m.max_step, 4)}
            for m in movers[:5]
        ],
        "top_edges": edges[:5],
        "backtest": {k: v for k, v in bt.items() if k != "detail"},
        "backtest_bets": bt["detail"],
    }


def render_text(report: dict) -> str:
    lines = ["PREDICTION MARKETS — DAILY RESEARCH REPORT", ""]
    dq = report["data_quality"]
    lines.append(f"Data quality: {dq['kept']} of {dq['total']} snapshots kept; "
                 f"{dq['duplicates']} duplicates, {dq['missing_odds']} missing odds, "
                 f"{dq['stale']} stale rows quarantined.")
    lines.append("")
    lines.append("Biggest market movers (consensus home probability, first to last):")
    for m in report["top_movers"]:
        lines.append(f"  {m['label']}: {m['move']:+.3f} (largest single step {m['max_step']:.3f})")
    lines.append("")
    lines.append("Largest model-vs-market edges (latest snapshot):")
    for e in report["top_edges"]:
        lines.append(f"  {e['label']}: model {e['model_home']:.2f} vs market "
                     f"{e['market_home']:.2f} (edge {e['edge_home']:+.3f})")
    lines.append("")
    bt = report["backtest"]
    lines.append(f"Backtest (flat $100 stakes, 5% edge threshold): {bt['bets']} bets, "
                 f"profit ${bt['profit']:.2f} on ${bt['staked']:.0f} staked "
                 f"(ROI {bt['roi']:.1%}, hit rate {bt['hit_rate']:.1%}).")
    return "\n".join(lines) + "\n"


def write_reports(report: dict, json_path: str, text_path: str) -> None:
    with open(json_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    with open(text_path, "w") as fh:
        fh.write(render_text(report))
