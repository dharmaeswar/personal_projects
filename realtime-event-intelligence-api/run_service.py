"""Run the event intelligence service locally.

Seeds a stream with synthetic event signals, runs the consumer once,
then serves the REST API.

Usage:
    python run_service.py            # listens on http://127.0.0.1:8000
    python run_service.py 9000       # custom port
"""

import sys

from event_intel.api import run as serve
from event_intel.pipeline import run_consumer
from event_intel.store import EventStore
from event_intel.stream import StreamTopic

SEED_SIGNALS = [
    {
        "source_id": "wire-1",
        "event_type": "outage",
        "text": "Power outage reported downtown",
        "reliability": 0.9,
        "keyword_severity": 0.8,
        "corroborations": 3,
        "age_seconds": 120,
    },
    {
        "source_id": "wire-2",
        "event_type": "outage",
        "text": "Power outage reported downtown",
        "reliability": 0.85,
        "keyword_severity": 0.8,
        "corroborations": 2,
        "age_seconds": 180,
    },
    {
        "source_id": "wire-1",
        "event_type": "outage",
        "text": "Power outage reported downtown",
        "reliability": 0.9,
        "keyword_severity": 0.8,
        "corroborations": 3,
        "age_seconds": 120,
    },
    {
        "source_id": "sensor-7",
        "event_type": "weather",
        "text": "Heavy rain expected this evening",
        "reliability": 0.6,
        "keyword_severity": 0.3,
        "corroborations": 0,
        "age_seconds": 900,
    },
    {
        "source_id": "wire-3",
        "event_type": "cyber",
        "text": "Credential stuffing attempts against login portal",
        "reliability": 0.95,
        "keyword_severity": 0.9,
        "corroborations": 5,
        "age_seconds": 60,
    },
]


def main(port: int) -> None:
    topic = StreamTopic("event-signals", partitions=3)
    for signal in SEED_SIGNALS:
        topic.publish(signal["source_id"], signal)
    store = EventStore()
    stats = run_consumer(topic, store, group="alert-workers")
    print("consumer run:", stats)
    print("store:", store.counts())
    serve(port, store=store)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
