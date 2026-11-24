"""Run the DataCraft-style streaming ingestion platform demo.

Writes ``datacraft_report.txt`` next to this script. All data is synthetic
and seeded; the streaming, routing, health and catalog steps run locally
with pandas — no Flink cluster, Kinesis stream, S3 bucket, Redshift
warehouse or Andes/EDX sink is involved.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from lakehouse.datacraft import (
    PRODUCTION_FLEET_SIZE,
    SOURCES,
    build_catalog,
    generate_pipeline_registry,
    ingest_source,
    monitor_pipelines,
    route_to_sinks,
    run_datacraft,
    search_catalog,
)

HERE = Path(__file__).resolve().parent


def main() -> None:
    out = run_datacraft()
    registry = out["registry"]
    health = out["health"]
    catalog = out["catalog"]
    lines = ["DATACRAFT-STYLE STREAMING INGESTION REPORT", ""]
    lines.append(f"Registered pipelines (demo fleet): {len(registry)}")
    lines.append(f"Production fleet size modelled: ~{PRODUCTION_FLEET_SIZE:,}")
    lines.append(f"Sources: {', '.join(SOURCES)}; sinks: S3, Andes, EDX")
    lines.append("")
    lines.append(f"Events arrived: {out['total_arrived']}")
    lines.append(f"Events accepted: {out['total_accepted']}")
    lines.append(f"Duplicates dropped (exactly-once): {out['total_duplicates']}")
    lines.append(f"Late events dropped at watermark: {out['total_late']}")
    lines.append("")
    lines.append("Rows landed per sink:")
    for sink, rows in out["sink_rows"].items():
        lines.append(f"  {sink}: {rows}")
    lines.append("")
    status_counts = health["status"].value_counts().to_dict()
    lines.append("Pipeline health (as of 10 min after newest event):")
    for status in ("HEALTHY", "DEGRADED", "STALLED"):
        lines.append(f"  {status}: {status_counts.get(status, 0)}")
    lines.append("")
    lines.append(f"Catalog tables registered: {len(catalog)}")
    hits = search_catalog(catalog, "orders")
    lines.append(f"Catalog search 'orders': {len(hits)} table(s) — {', '.join(hits['table'])}")
    lines.append("")
    lines.append("Sink manifest (first 10 rows):")
    lines.append(out["manifest"].head(10).to_string(index=False))
    (HERE / "datacraft_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
