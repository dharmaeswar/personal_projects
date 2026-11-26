"""End-to-end demo run of the personalization training-dataset pipeline.

Generates seeded synthetic events, cleanses them, builds point-in-time
correct training rows, splits them by date, writes the bronze / silver /
gold medallion layers, builds the star schema, and prints a run summary.

Run:  python run_pipeline.py [--out data] [--impressions 400]
"""

from __future__ import annotations

import argparse
import json

from personalization_data import cost, datasets, events, features, modeling, orchestration, quality


def main() -> None:
    parser = argparse.ArgumentParser(description="Personalization training-dataset pipeline")
    parser.add_argument("--out", default="data", help="output directory for medallion layers")
    parser.add_argument("--impressions", type=int, default=400)
    args = parser.parse_args()

    raw = events.generate_events(n_impressions=args.impressions)
    clean, quarantined = quality.cleanse(raw)
    report = quality.quality_report(clean, quarantined)
    rows = features.build_training_rows(clean)
    splits = datasets.time_split(rows)
    manifest = datasets.write_medallion(raw, clean, rows, args.out)

    dim_user = modeling.build_dim_user(clean)
    dim_content = modeling.build_dim_content(clean)
    dim_date = modeling.build_dim_date(clean)
    fact = modeling.build_fact_interactions(clean, dim_user, dim_content)

    dag = orchestration.DagRun(
        orchestration.TASKS,
        {t["name"]: (lambda: None) for t in orchestration.TASKS},
    )
    dag_results = dag.run()
    cost_advice = cost.advise(rows, partition_col="content_id")

    summary = {
        "raw_events": len(raw),
        "clean_events": len(clean),
        "quarantined_events": len(quarantined),
        "quarantine_rate": report["quarantine_rate"],
        "training_rows": len(rows),
        "label_rates": features.label_rates(rows),
        "splits": {name: len(frame) for name, frame in splits.items()},
        "manifest_fingerprint": manifest["fingerprint"],
        "star_schema": {
            "dim_user": len(dim_user),
            "dim_content": len(dim_content),
            "dim_date": len(dim_date),
            "fact_interactions": len(fact),
        },
        "dag": dag_results,
        "cost": cost_advice,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
