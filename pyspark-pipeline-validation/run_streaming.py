"""Run the streaming CDC job and write the streaming report."""
from pathlib import Path

from spark_pipeline.streaming import run_streaming

ROOT = Path(__file__).resolve().parent


def main():
    summary, state, dlq = run_streaming(ROOT)
    lines = [
        "Streaming CDC report (Kafka-style micro-batches, local stand-in)",
        f"events={summary['events']} micro_batches={summary['micro_batches']}",
        f"inserts={summary['inserts']} updates={summary['updates']} "
        f"deletes={summary['deletes']} late_dropped={summary['late_dropped']} "
        f"dlq={summary['dlq']}",
        f"final_rows={summary['final_rows']} "
        f"final_revenue=${summary['final_revenue']:,.2f}",
        f"watermark={summary['watermark']}",
    ]
    for batch, counts in summary["batch_counts"].items():
        lines.append(f"batch {batch}: {counts}")
    if len(dlq):
        lines.append("dead-letter queue:")
        for _, row in dlq.iterrows():
            lines.append(f"  {row['event_id']} op={row['op']}: {row['violation']}")
    (ROOT / "streaming_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
