"""Manufacturing telemetry data platform: streaming ingest, multi-store
abstraction, analytics and a reporting API for additive-manufacturing
machine telemetry. All data is synthetic and seeded.
"""

from .analytics import daily_report, find_anomalies, machine_summary
from .api import (get_daily_report, get_machine_summary, latest_reading,
                  list_anomalies, report_as_json)
from .stores import (CacheStore, DataPlatform, DocumentStore,
                     RelationalStore, TelemetryReading, TimeSeriesStore)
from .stream import Record, Topic

__all__ = [
    "CacheStore", "DataPlatform", "DocumentStore", "Record",
    "RelationalStore", "TelemetryReading", "TimeSeriesStore", "Topic",
    "daily_report", "find_anomalies", "get_daily_report",
    "get_machine_summary", "latest_reading", "list_anomalies",
    "machine_summary", "report_as_json",
]
