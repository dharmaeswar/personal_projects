"""Dataset catalog generation: the publish step regenerates the catalog
from the warehouse that actually ran, so docs never describe tables
that do not exist."""

from __future__ import annotations


def generate_catalog(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    lines = ["# Marketplace Intelligence — Dataset Catalog", ""]
    for (name,) in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
        lines.append(f"## {name} ({count} rows)")
        for col in cols:
            lines.append(f"- {col[1]} ({col[2]})")
        lines.append("")
    return "\n".join(lines)
