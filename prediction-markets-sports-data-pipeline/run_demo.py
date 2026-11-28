"""End-to-end demo: generate the feed, stream it, cleanse, store, report.

Writes ``demo_out/``: the raw feed CSV, the cleansed store (partitioned
columnar ``.npz`` + manifest), and the JSON + text research reports.
Prints the headline numbers.
"""

import os

from prediction_markets import build_report, cleanse, generate_feed, write_store, write_reports
from prediction_markets.ingest import write_feed_csv
from prediction_markets.stream import Consumer, Topic

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_out")


def main() -> dict:
    os.makedirs(OUT, exist_ok=True)
    feed = generate_feed()
    write_feed_csv(feed, os.path.join(OUT, "raw_feed.csv"))

    topic = Topic("sports-odds")
    for snap in feed:
        topic.produce(snap)
    consumer = Consumer(topic, group="research")
    streamed = consumer.poll()

    records, report = cleanse(streamed)
    manifest = write_store(records, os.path.join(OUT, "store"))
    result = build_report(records, report)
    write_reports(result, os.path.join(OUT, "report.json"),
                  os.path.join(OUT, "report.txt"))
    print(f"feed rows: {len(feed)} | streamed: {len(streamed)} | "
          f"kept: {report.kept} | quarantined: {len(report.quarantined)}")
    print(f"partitions: {len(manifest)} | events: {result['events']}")
    bt = result["backtest"]
    print(f"backtest: {bt['bets']} bets, profit ${bt['profit']:.2f}, "
          f"ROI {bt['roi']:.1%}, hit rate {bt['hit_rate']:.1%}")
    return result


if __name__ == "__main__":
    main()
