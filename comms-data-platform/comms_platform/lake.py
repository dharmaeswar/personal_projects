"""Local lakehouse: bronze -> silver -> gold on Parquet files.

This is a local model of the serverless lake the real platform runs on S3:
bronze holds raw ingest (nothing cleaned), silver holds cleaned, deduped
tables with bad rows quarantined, gold holds business aggregates. Every
write appends a versioned entry to a Delta-style transaction log
(`_delta_log.json`), so any table can be traced back to the write that
produced it. Schema enforcement rejects writes that violate the expected
schema before they land.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SCHEMAS = {
    "messages": {
        "message_id": "string",
        "campaign_id": "string",
        "campaign_name": "string",
        "channel": "string",
        "subject": "string",
        "send_date": "string",
        "audience_size": "int64",
    },
    "metrics": {
        "campaign_id": "string",
        "event_date": "string",
        "opens": "int64",
        "clicks": "int64",
        "unsubscribes": "int64",
    },
    "daily_engagement": {
        "event_date": "string",
        "campaign_id": "string",
        "channel": "string",
        "messages_sent": "int64",
        "total_opens": "int64",
        "total_clicks": "int64",
        "open_rate": "float64",
    },
}


class SchemaViolation(ValueError):
    pass


class Lake:
    """A three-layer lake rooted at a local directory (stands in for S3)."""

    def __init__(self, root):
        self.root = Path(root)
        for layer in ("bronze", "silver", "gold"):
            (self.root / layer).mkdir(parents=True, exist_ok=True)

    def _path(self, layer, name):
        return self.root / layer / f"{name}.parquet"

    def _log_path(self, layer, name):
        return self.root / layer / f"{name}_delta_log.json"

    def write_table(self, layer, name, df, operation="write"):
        expected = SCHEMAS.get(name)
        if expected is not None:
            missing = [c for c in expected if c not in df.columns]
            if missing:
                raise SchemaViolation(f"{name}: missing columns {missing}")
            # Coerce to the declared schema (pandas builds object columns
            # from plain dicts); a failed cast is a schema violation.
            df = df.copy()
            for col, dtype in expected.items():
                try:
                    df[col] = df[col].astype(dtype)
                except (ValueError, TypeError) as exc:
                    raise SchemaViolation(
                        f"{name}: column {col} cannot be cast to {dtype}: {exc}"
                    )
        path = self._path(layer, name)
        df.to_parquet(path, index=False)
        log_path = self._log_path(layer, name)
        entries = json.loads(log_path.read_text()) if log_path.exists() else []
        entries.append(
            {
                "version": len(entries) + 1,
                "operation": operation,
                "rows": int(len(df)),
                "table": name,
                "layer": layer,
            }
        )
        log_path.write_text(json.dumps(entries, indent=2))
        return path

    def read_table(self, layer, name):
        path = self._path(layer, name)
        if not path.exists():
            raise FileNotFoundError(f"no {layer} table {name} at {path}")
        return pd.read_parquet(path)

    def table_exists(self, layer, name):
        return self._path(layer, name).exists()

    def log_entries(self, layer, name):
        log_path = self._log_path(layer, name)
        if not log_path.exists():
            return []
        return json.loads(log_path.read_text())
