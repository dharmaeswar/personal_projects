"""Seeded demo: stream synthetic WAAM-printer telemetry through the
platform and print the daily report.

Run:  python run_demo.py
"""

from __future__ import annotations

import random

from telemetry_platform import DataPlatform, TelemetryReading, Topic
from telemetry_platform.api import report_as_json

MACHINES = {
    "WAAM-01": {"type": "waam_printer", "nozzle_mm": 4.0, "site": "long-beach"},
    "WAAM-02": {"type": "waam_printer", "nozzle_mm": 6.0, "site": "long-beach"},
    "WELD-01": {"type": "weld_repair_robot", "nozzle_mm": 2.5, "site": "long-beach"},
}

DAY = 86_400
START = 1_793_000_000  # fixed seed epoch; synthetic data only


def seed_readings(seed: int = 42) -> list[TelemetryReading]:
    rng = random.Random(seed)
    readings: list[TelemetryReading] = []
    for machine_id in MACHINES:
        for step in range(240):  # 240 readings per machine, 12 min apart
            ts = START + step * 720
            temp = 820 + rng.gauss(0, 25)
            vibration = 4.5 + abs(rng.gauss(0, 1.5))
            current = 250 + rng.gauss(0, 15)
            if step == 100 and machine_id == "WAAM-01":
                temp = 985.0  # seeded over-temperature event
            if step == 150 and machine_id == "WELD-01":
                vibration = 14.8  # seeded vibration spike
            readings.append(TelemetryReading(
                machine_id=machine_id, ts=ts, temp_c=round(temp, 1),
                vibration_mm_s=round(vibration, 2),
                weld_current_a=round(current, 1),
                layer=step // 40 + 1,
                status="printing" if step % 60 else "calibrating",
            ))
    return readings


def main() -> None:
    platform = DataPlatform()
    topic = Topic("machine-telemetry", partitions=4)
    for machine_id, doc in MACHINES.items():
        platform.register_machine(machine_id, doc)
    for reading in seed_readings():
        record = topic.publish(reading.machine_id, reading.__dict__)
        assert record.offset >= 0
    consumed_total = 0
    while topic.lag("platform-ingest") > 0:
        consumed = topic.poll("platform-ingest", max_records=500)
        for record in consumed:
            platform.ingest(TelemetryReading(**record.value))
        topic.commit("platform-ingest", consumed)
        consumed_total += len(consumed)
    print(f"streamed {topic.size()} records; consumed {consumed_total};"
          f" consumer lag now {topic.lag('platform-ingest')}")
    print(f"stored {platform.timeseries.count()} measurements")
    print(report_as_json(platform, list(MACHINES),
                         START, START + 2 * DAY))
    platform.close()


if __name__ == "__main__":
    main()
