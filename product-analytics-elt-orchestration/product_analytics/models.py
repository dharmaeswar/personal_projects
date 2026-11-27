"""dbt-style modeling layer: staging -> intermediate -> mart models.

Mirrors how a dbt project works on BigQuery, run locally on SQLite:

- Models are plain SQL files under ``models/`` (staging, intermediate,
  marts/gaming, marts/ads). A model references an upstream model with
  ``{{ ref('model_name') }}``; the runner replaces the ref with the table
  name and runs the models in the order declared in ``models/schema.yml``.
- Tests are declared in ``models/schema.yml`` (unique, not_null,
  relationships, accepted_values, non_negative) and enforced on every
  build; results land in ``model_test_results`` and a failed test raises.
- ``configs/semantic_layer.yaml`` holds shared metric definitions (one
  definition per metric, naming the mart it is defined on); the runner
  validates that each metric's model exists and every column it references
  is a real column of that mart.
- Squad sources are synthetic and seeded deterministically: a third-party
  game catalog (SensorTower-style fields) and ad delivery events, plus
  per-user play sessions. No real user, game, or advertiser data is used.

BigQuery note: the SQL is standard SQL except the ``event_date``
extraction in ``stg_events`` (``substr(event_ts, 1, 10)`` here; ``DATE()``
on BigQuery). Nothing else is SQLite-specific.
"""
from __future__ import annotations

import os
import random
import re
import sqlite3

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE, "models")
SCHEMA_PATH = os.path.join(MODELS_DIR, "schema.yml")
SEMANTIC_PATH = os.path.join(BASE, "configs", "semantic_layer.yaml")

REF_RE = re.compile(r"\{\{\s*ref\('([^']+)'\)\s*\}\}")

# Synthetic third-party game catalog (game_id, title, publisher, genre,
# platform, store_rank, first_seen_date). Titles and publishers are invented.
GAMES = [
    ("g001", "Starfall Arena", "Nova Play", "Action", "PC", 3, "2026-01-05"),
    ("g002", "Dungeon Draft", "Pixel Forge", "RPG", "PC", 7, "2026-02-11"),
    ("g003", "Hex Merge", "Tiny Orbit", "Puzzle", "Mobile", 1, "2026-01-19"),
    ("g004", "Grand Prix Rivals", "Velocity Works", "Sports", "Console", 5, "2026-03-02"),
    ("g005", "Kingdom Tactics", "Banner & Sword", "Strategy", "PC", 9, "2026-02-27"),
    ("g006", "Neon Drift", "Velocity Works", "Action", "Mobile", 12, "2026-04-08"),
    ("g007", "Farmstead Friends", "Tiny Orbit", "Puzzle", "Mobile", 4, "2026-03-15"),
    ("g008", "Iron League", "Nova Play", "Sports", "Console", 18, "2026-05-21"),
]

CAMPAIGNS = [
    ("cmp_quest", "Quest Launch", "search"),
    ("cmp_quest", "Quest Launch", "video"),
    ("cmp_guild", "Guild Nights", "video"),
    ("cmp_guild", "Guild Nights", "social"),
    ("cmp_arena", "Arena Pass", "display"),
    ("cmp_arena", "Arena Pass", "search"),
    ("cmp_coop", "Co-op Weekend", "social"),
    ("cmp_coop", "Co-op Weekend", "video"),
]

DATES = ["2026-11-0%d" % d for d in range(8, 15)]  # 2026-11-08 .. 2026-11-14


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_semantic_layer() -> dict:
    with open(SEMANTIC_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def find_model_sql(name: str) -> str:
    for root, _, files in os.walk(MODELS_DIR):
        if name + ".sql" in files:
            with open(os.path.join(root, name + ".sql"), encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError(f"no model SQL found for {name}")


def resolve_refs(sql: str, built: set[str]) -> str:
    """Replace {{ ref('name') }} with the table name; refs must be built already."""

    def repl(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in built:
            raise ValueError(f"model ref '{name}' is not built yet (check schema.yml order)")
        return name

    return REF_RE.sub(repl, sql)


def seed_squad_sources(conn: sqlite3.Connection) -> dict:
    """Seed the deterministic synthetic squad sources (idempotent)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS game_catalog_raw (
            game_id TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT NOT NULL,
            genre TEXT NOT NULL, platform TEXT NOT NULL, store_rank INTEGER NOT NULL,
            first_seen_date TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ads_raw (
            campaign_id TEXT NOT NULL, campaign_name TEXT NOT NULL,
            channel TEXT NOT NULL, event_date TEXT NOT NULL,
            impressions INTEGER NOT NULL, clicks INTEGER NOT NULL,
            spend_usd REAL NOT NULL,
            PRIMARY KEY (campaign_id, channel, event_date))"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS game_sessions_raw (
            session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            game_id TEXT NOT NULL, session_date TEXT NOT NULL,
            duration_sec INTEGER NOT NULL, event_count INTEGER NOT NULL)"""
    )
    conn.execute("DELETE FROM game_catalog_raw")
    conn.executemany("INSERT INTO game_catalog_raw VALUES (?,?,?,?,?,?,?)", GAMES)

    rng = random.Random(7)
    ads_rows = []
    for campaign_id, campaign_name, channel in CAMPAIGNS:
        for date in DATES:
            impressions = rng.randint(8_000, 60_000)
            clicks = int(impressions * rng.uniform(0.01, 0.04))
            spend = round(clicks * rng.uniform(0.40, 1.80), 2)
            ads_rows.append((campaign_id, campaign_name, channel, date,
                             impressions, clicks, spend))
    conn.execute("DELETE FROM ads_raw")
    conn.executemany("INSERT INTO ads_raw VALUES (?,?,?,?,?,?,?)", ads_rows)

    rng = random.Random(42)
    users = ["u%04d" % i for i in range(1, 121)]
    session_rows = []
    idx = 0
    for user in users:
        for date in DATES:
            if rng.random() < 0.55:  # plays on ~4 of 7 days
                for _ in range(rng.choice([1, 1, 2])):
                    idx += 1
                    game = rng.choice(GAMES)[0]
                    session_rows.append((
                        "s%05d" % idx, user, game, date,
                        rng.randint(300, 5400), rng.randint(5, 120),
                    ))
    conn.execute("DELETE FROM game_sessions_raw")
    conn.executemany("INSERT INTO game_sessions_raw VALUES (?,?,?,?,?,?)", session_rows)
    conn.commit()
    return {"games": len(GAMES), "ads_rows": len(ads_rows), "sessions": len(session_rows)}


def run_test(conn: sqlite3.Connection, model: str, test: dict) -> dict:
    """Run one declared schema test against a built model table."""
    kind = test["type"]
    cols = test.get("columns") or ([test["column"]] if "column" in test else [])
    label = f"{model}.{kind}({','.join(cols)})"
    if kind == "unique":
        group = ", ".join(cols)
        bad = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {group} FROM {model} "
            f"GROUP BY {group} HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        detail = f"{bad} duplicated key groups"
    elif kind == "not_null":
        col = cols[0]
        bad = conn.execute(
            f"SELECT COUNT(*) FROM {model} WHERE {col} IS NULL OR {col} = ''"
        ).fetchone()[0]
        detail = f"{bad} null/empty values in {col}"
    elif kind == "relationships":
        col, to, field = test["column"], test["to"], test["field"]
        bad = conn.execute(
            f"SELECT COUNT(*) FROM {model} m LEFT JOIN {to} t "
            f"ON t.{field} = m.{col} WHERE t.{field} IS NULL"
        ).fetchone()[0]
        detail = f"{bad} rows with no match in {to}.{field}"
    elif kind == "accepted_values":
        col = cols[0]
        allowed = ", ".join(f"'{v}'" for v in test["values"])
        bad = conn.execute(
            f"SELECT COUNT(*) FROM {model} WHERE {col} NOT IN ({allowed})"
        ).fetchone()[0]
        detail = f"{bad} rows outside {test['values']}"
    elif kind == "non_negative":
        col = cols[0]
        bad = conn.execute(
            f"SELECT COUNT(*) FROM {model} WHERE {col} IS NOT NULL AND {col} < 0"
        ).fetchone()[0]
        detail = f"{bad} negative values in {col}"
    else:
        raise ValueError(f"unknown test type: {kind}")
    return {"model": model, "test": label, "status": "pass" if bad == 0 else "fail",
            "detail": detail}


def run_schema_tests(conn: sqlite3.Connection, schema: dict) -> list[dict]:
    results = []
    for model in schema["models"]:
        for test in model.get("tests", []):
            results.append(run_test(conn, model["name"], test))
    return results


def check_freshness(conn: sqlite3.Connection, schema: dict, latest_date: str) -> dict:
    fresh = schema.get("freshness", {})
    model, column = fresh.get("model", "stg_events"), fresh.get("column", "event_date")
    newest = conn.execute(f"SELECT MAX({column}) FROM {model}").fetchone()[0]
    passed = newest == latest_date
    return {"model": model, "test": f"freshness({column})",
            "status": "pass" if passed else "fail",
            "detail": f"newest {column} {newest}, expected {latest_date}"}


def validate_semantic_layer(conn: sqlite3.Connection) -> list[dict]:
    """Every semantic metric must name a real mart with real columns."""
    schema = load_schema()
    model_names = {m["name"] for m in schema["models"]}
    layer = load_semantic_layer()
    results = []
    for name, meta in layer["metrics"].items():
        model = meta["model"]
        if model not in model_names:
            results.append({"metric": name, "status": "fail",
                            "detail": f"unknown model {model}"})
            continue
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({model})")}
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", meta["sql"]))
        missing = sorted(t for t in tokens
                         if t not in columns
                         and t.upper() not in ("SUM", "AVG", "COUNT", "NULLIF"))
        if missing:
            results.append({"metric": name, "status": "fail",
                            "detail": f"unknown columns {missing} in {model}"})
        else:
            results.append({"metric": name, "status": "pass",
                            "detail": f"defined on {model}"})
    return results


def build_models(conn: sqlite3.Connection, latest_date: str = "2026-11-14") -> dict:
    """Seed squad sources, build every model in schema order, test, document."""
    seeded = seed_squad_sources(conn)
    schema = load_schema()
    built: set[str] = set()
    row_counts: dict[str, int] = {}
    for model in schema["models"]:
        name = model["name"]
        sql = resolve_refs(find_model_sql(name), built)
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.execute(f"CREATE TABLE {name} AS {sql}")
        row_counts[name] = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        built.add(name)
    results = run_schema_tests(conn, schema)
    results.append(check_freshness(conn, schema, latest_date))
    semantic = validate_semantic_layer(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS model_test_results (
            model_name TEXT NOT NULL, test_name TEXT NOT NULL,
            status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (model_name, test_name))"""
    )
    for r in results:
        conn.execute(
            "INSERT OR REPLACE INTO model_test_results "
            "(model_name, test_name, status, detail) VALUES (?, ?, ?, ?)",
            (r["model"], r["test"], r["status"], r["detail"]),
        )
    conn.commit()
    generate_model_docs(conn, os.path.join(BASE, "MODELS.md"), schema, results, semantic)
    failed = [r for r in results if r["status"] == "fail"]
    failed_semantic = [s for s in semantic if s["status"] == "fail"]
    if failed or failed_semantic:
        raise RuntimeError(
            f"model tests failed: {[r['test'] for r in failed]}; "
            f"semantic layer failures: {[s['metric'] for s in failed_semantic]}"
        )
    return {"seeded": seeded, "row_counts": row_counts,
            "tests": results, "semantic": semantic}


def generate_model_docs(conn: sqlite3.Connection, path: str, schema: dict,
                        results: list[dict], semantic: list[dict]) -> str:
    lines = ["# Model Documentation (dbt-style layer)\n"]
    lines.append("Generated by the build_models step. Models, tests and semantic")
    lines.append("metrics below always describe the warehouse that actually ran.\n")
    lines.append("## Models\n")
    for model in schema["models"]:
        name = model["name"]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        except sqlite3.Error:
            count = -1
        lines.append(f"- **{name}** — {count} rows — {model['description']}")
    lines.append("\n## Schema tests\n")
    for r in results:
        lines.append(f"- {r['model']}.{r['test']}: {r['status']} — {r['detail']}")
    lines.append("\n## Semantic layer (shared metric definitions)\n")
    for s in semantic:
        lines.append(f"- {s['metric']}: {s['status']} — {s['detail']}")
    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text
