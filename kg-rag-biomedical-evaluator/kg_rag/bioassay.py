"""Bioassay ETL, SQL warehouse, knowledge-graph extension and dashboard.

November 2026 update for an AbbVie Associate Data Scientist II
(Early Discovery Science) application: the same knowledge graph the
project already builds from biomedical literature, extended with the
thing the AbbVie role stewards — a bioassay knowledge graph.

What it does, end to end:
- ETL: seeded synthetic bioassay results are validated (IC50 must be
  positive, at least 2 replicates, Z-prime present), cleaned, and loaded.
- SQL: the clean rows go into SQLite tables (table creation, joins,
  a view of potent QC-passed compounds, reporting queries) — the exact
  SQL surface the posting asks for (basic queries, table creation,
  views, reporting).
- Knowledge graph: each assay becomes an Assay node; the tested compound
  links to it (TESTED_IN) and it links to its target gene/protein
  (MEASURES), so a scientist can walk compound -> assay -> target.
- Dashboard: a static HTML dashboard (the analysis a Spotfire / Power BI /
  Tableau dashboard would show) plus a CSV report, built from the same
  queries — median IC50 per target, hit rate per assay type, QC summary.

Honest note: all compounds, targets, assay values and dates are synthetic
and invented for this demo. No real AbbVie data, no real assay data and no
real patient data is used. IC50 thresholds (potent < 100 nM) are demo
cutoffs, not a real screening policy. This is a demo built to show the
ETL, SQL, graph and dashboard work, not a claim of real drug discovery.
"""

import csv
import html
import json
import sqlite3
import statistics
from collections import defaultdict

MIN_REPLICATES = 2
POTENT_IC50_NM = 100.0

# Seeded synthetic bioassay results. Compounds and targets reuse the
# lexicon in kg_rag/graph.py so the graph extension links to real nodes.
BIOASSAY_RESULTS = [
    {"result_id": "BA-001", "assay_id": "ASY-101", "assay_type": "Biochemical binding",
     "compound": "Olaparib", "target": "BRCA1", "target_type": "Gene",
     "ic50_nm": 42.0, "hill_slope": 1.1, "replicates": 3, "plate_id": "P-01",
     "run_date": "2026-11-02", "z_prime": 0.72, "qc_pass": True},
    {"result_id": "BA-002", "assay_id": "ASY-101", "assay_type": "Biochemical binding",
     "compound": "Olaparib", "target": "BRCA1", "target_type": "Gene",
     "ic50_nm": 55.0, "hill_slope": 1.0, "replicates": 3, "plate_id": "P-01",
     "run_date": "2026-11-02", "z_prime": 0.72, "qc_pass": True},
    {"result_id": "BA-003", "assay_id": "ASY-102", "assay_type": "Enzymatic inhibition",
     "compound": "Osimertinib", "target": "EGFR", "target_type": "Gene",
     "ic50_nm": 8.5, "hill_slope": 0.9, "replicates": 4, "plate_id": "P-02",
     "run_date": "2026-11-03", "z_prime": 0.81, "qc_pass": True},
    {"result_id": "BA-004", "assay_id": "ASY-102", "assay_type": "Enzymatic inhibition",
     "compound": "Osimertinib", "target": "EGFR", "target_type": "Gene",
     "ic50_nm": 12.0, "hill_slope": 1.2, "replicates": 4, "plate_id": "P-02",
     "run_date": "2026-11-03", "z_prime": 0.81, "qc_pass": True},
    {"result_id": "BA-005", "assay_id": "ASY-103", "assay_type": "Cell viability",
     "compound": "Trastuzumab", "target": "HER2", "target_type": "Protein",
     "ic50_nm": 210.0, "hill_slope": 1.0, "replicates": 3, "plate_id": "P-03",
     "run_date": "2026-11-04", "z_prime": 0.68, "qc_pass": True},
    {"result_id": "BA-006", "assay_id": "ASY-103", "assay_type": "Cell viability",
     "compound": "Trastuzumab", "target": "HER2", "target_type": "Protein",
     "ic50_nm": 185.0, "hill_slope": 1.3, "replicates": 3, "plate_id": "P-03",
     "run_date": "2026-11-04", "z_prime": 0.68, "qc_pass": True},
    {"result_id": "BA-007", "assay_id": "ASY-104", "assay_type": "Biochemical binding",
     "compound": "Pembrolizumab", "target": "PD-L1", "target_type": "Protein",
     "ic50_nm": 96.0, "hill_slope": 1.1, "replicates": 2, "plate_id": "P-04",
     "run_date": "2026-11-05", "z_prime": 0.61, "qc_pass": True},
    {"result_id": "BA-008", "assay_id": "ASY-104", "assay_type": "Biochemical binding",
     "compound": "Pembrolizumab", "target": "PD-L1", "target_type": "Protein",
     "ic50_nm": 340.0, "hill_slope": 0.8, "replicates": 2, "plate_id": "P-04",
     "run_date": "2026-11-05", "z_prime": 0.61, "qc_pass": True},
    {"result_id": "BA-009", "assay_id": "ASY-105", "assay_type": "Enzymatic inhibition",
     "compound": "Dabrafenib", "target": "BRAF", "target_type": "Gene",
     "ic50_nm": 3.2, "hill_slope": 1.0, "replicates": 3, "plate_id": "P-05",
     "run_date": "2026-11-06", "z_prime": 0.77, "qc_pass": True},
    {"result_id": "BA-010", "assay_id": "ASY-105", "assay_type": "Enzymatic inhibition",
     "compound": "Dabrafenib", "target": "BRAF", "target_type": "Gene",
     "ic50_nm": 4.1, "hill_slope": 1.1, "replicates": 3, "plate_id": "P-05",
     "run_date": "2026-11-06", "z_prime": 0.77, "qc_pass": True},
    {"result_id": "BA-011", "assay_id": "ASY-106", "assay_type": "Cell viability",
     "compound": "Donanemab", "target": "amyloid-beta", "target_type": "Protein",
     "ic50_nm": 1200.0, "hill_slope": 0.9, "replicates": 3, "plate_id": "P-06",
     "run_date": "2026-11-07", "z_prime": 0.55, "qc_pass": True},
    {"result_id": "BA-012", "assay_id": "ASY-106", "assay_type": "Cell viability",
     "compound": "Donanemab", "target": "amyloid-beta", "target_type": "Protein",
     "ic50_nm": 980.0, "hill_slope": 1.0, "replicates": 3, "plate_id": "P-06",
     "run_date": "2026-11-07", "z_prime": 0.55, "qc_pass": True},
    {"result_id": "BA-013", "assay_id": "ASY-107", "assay_type": "Biochemical binding",
     "compound": "Olaparib", "target": "BRCA1", "target_type": "Gene",
     "ic50_nm": 61.0, "hill_slope": 1.2, "replicates": 2, "plate_id": "P-07",
     "run_date": "2026-11-09", "z_prime": 0.31, "qc_pass": False},
    {"result_id": "BA-014", "assay_id": "ASY-107", "assay_type": "Biochemical binding",
     "compound": "Olaparib", "target": "BRCA1", "target_type": "Gene",
     "ic50_nm": 48.0, "hill_slope": 1.0, "replicates": 2, "plate_id": "P-07",
     "run_date": "2026-11-09", "z_prime": 0.31, "qc_pass": False},
    # Deliberately dirty rows: rejected by validation, never loaded.
    {"result_id": "BA-015", "assay_id": "ASY-108", "assay_type": "Enzymatic inhibition",
     "compound": "Osimertinib", "target": "EGFR", "target_type": "Gene",
     "ic50_nm": -5.0, "hill_slope": 1.0, "replicates": 3, "plate_id": "P-08",
     "run_date": "2026-11-10", "z_prime": 0.80, "qc_pass": True},
    {"result_id": "BA-016", "assay_id": "ASY-108", "assay_type": "Enzymatic inhibition",
     "compound": "Osimertinib", "target": "EGFR", "target_type": "Gene",
     "ic50_nm": 9.0, "hill_slope": 1.0, "replicates": 1, "plate_id": "P-08",
     "run_date": "2026-11-10", "z_prime": 0.80, "qc_pass": True},
]


def validate_row(row):
    """Return a list of validation problems; empty means the row is clean."""
    problems = []
    if row["ic50_nm"] is None or row["ic50_nm"] <= 0:
        problems.append("ic50_nm must be positive")
    if row["replicates"] < MIN_REPLICATES:
        problems.append(f"replicates must be >= {MIN_REPLICATES}")
    if row["z_prime"] is None or not 0.0 <= row["z_prime"] <= 1.0:
        problems.append("z_prime must be between 0 and 1")
    if not row["assay_id"] or not row["compound"] or not row["target"]:
        problems.append("assay_id, compound and target are required")
    return problems


def clean_results(rows):
    """Split seeded rows into (clean, rejected); rejected keeps its reasons."""
    clean, rejected = [], []
    for row in rows:
        problems = validate_row(row)
        if problems:
            rejected.append({"result_id": row["result_id"], "reasons": problems})
        else:
            clean.append(row)
    return clean, rejected


def load_sqlite(clean, db_path):
    """Create tables + views and load clean rows; return the connection."""
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS bioassay_results")
    conn.execute("DROP TABLE IF EXISTS assays")
    conn.execute("DROP VIEW IF EXISTS v_potent_compounds")
    conn.execute("""CREATE TABLE assays (
        assay_id TEXT PRIMARY KEY, assay_type TEXT NOT NULL,
        target TEXT NOT NULL, target_type TEXT NOT NULL,
        run_date TEXT NOT NULL, plate_id TEXT NOT NULL, z_prime REAL NOT NULL)""")
    conn.execute("""CREATE TABLE bioassay_results (
        result_id TEXT PRIMARY KEY, assay_id TEXT NOT NULL REFERENCES assays(assay_id),
        compound TEXT NOT NULL, ic50_nm REAL NOT NULL, hill_slope REAL NOT NULL,
        replicates INTEGER NOT NULL, qc_pass INTEGER NOT NULL)""")
    assays = {}
    for row in clean:
        assays.setdefault(row["assay_id"], row)
    for assay in assays.values():
        conn.execute(
            "INSERT INTO assays VALUES (?, ?, ?, ?, ?, ?, ?)",
            (assay["assay_id"], assay["assay_type"], assay["target"],
             assay["target_type"], assay["run_date"], assay["plate_id"],
             assay["z_prime"]))
    for row in clean:
        conn.execute(
            "INSERT INTO bioassay_results VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row["result_id"], row["assay_id"], row["compound"], row["ic50_nm"],
             row["hill_slope"], row["replicates"], 1 if row["qc_pass"] else 0))
    conn.execute(f"""CREATE VIEW v_potent_compounds AS
        SELECT r.result_id, r.compound, a.target, a.assay_type, r.ic50_nm
        FROM bioassay_results r JOIN assays a ON r.assay_id = a.assay_id
        WHERE r.ic50_nm < {POTENT_IC50_NM} AND r.qc_pass = 1""")
    conn.commit()
    return conn


def report_queries(conn, clean):
    """Reporting queries over the warehouse; medians computed in Python."""
    by_target = defaultdict(list)
    for row in clean:
        if row["qc_pass"]:
            by_target[row["target"]].append(row["ic50_nm"])
    median_ic50_by_target = [
        {"target": t, "n": len(v), "median_ic50_nm": round(statistics.median(v), 1)}
        for t, v in sorted(by_target.items())]
    hit_rate = conn.execute(
        """SELECT a.assay_type, COUNT(*) AS n,
                  SUM(CASE WHEN r.ic50_nm < ? AND r.qc_pass = 1 THEN 1 ELSE 0 END)
                      AS potent
           FROM bioassay_results r JOIN assays a ON r.assay_id = a.assay_id
           GROUP BY a.assay_type ORDER BY a.assay_type""",
        (POTENT_IC50_NM,)).fetchall()
    hit_rate_by_assay_type = [
        {"assay_type": t, "n": n,
         "potent": p, "hit_rate": round(p / n, 3) if n else 0.0}
        for t, n, p in hit_rate]
    qc = conn.execute(
        "SELECT COUNT(*), SUM(qc_pass) FROM bioassay_results").fetchone()
    potent = conn.execute("SELECT * FROM v_potent_compounds").fetchall()
    return {
        "median_ic50_by_target": median_ic50_by_target,
        "hit_rate_by_assay_type": hit_rate_by_assay_type,
        "qc_summary": {"results": qc[0], "qc_passed": qc[1],
                       "qc_pass_rate": round(qc[1] / qc[0], 3) if qc[0] else 0.0},
        "potent_compounds": [
            {"result_id": r[0], "compound": r[1], "target": r[2],
             "assay_type": r[3], "ic50_nm": r[4]} for r in potent],
    }


def add_bioassay_edges(graph, clean):
    """Extend the knowledge graph with Assay nodes and bioassay edges.

    Compound -TESTED_IN-> Assay -MEASURES-> target gene/protein, with the
    assay run as the edge source so every bioassay edge keeps provenance.
    Returns (assays_added, edges_added).
    """
    assays = {}
    for row in clean:
        assays.setdefault(row["assay_id"], row)
    edges_added = 0
    for assay_id, assay in sorted(assays.items()):
        graph.add_edge(assay["compound"], "Drug", "TESTED_IN",
                       assay_id, "Assay", source=assay_id)
        graph.add_edge(assay_id, "Assay", "MEASURES",
                       assay["target"], assay["target_type"], source=assay_id)
        edges_added += 2
    return len(assays), edges_added


def write_report_csv(report, path):
    """Flat CSV of the potent-compounds view — the BI-tool input."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["result_id", "compound", "target", "assay_type", "ic50_nm"])
        for row in report["potent_compounds"]:
            writer.writerow([row["result_id"], row["compound"], row["target"],
                             row["assay_type"], row["ic50_nm"]])


def build_dashboard(report, path):
    """Static HTML dashboard: the tables a Spotfire/Power BI/Tableau
    dashboard would show, built from the same reporting queries."""
    def rows(cells):
        return "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
            for r in cells)
    body = "<h1>Bioassay Dashboard (synthetic demo data)</h1>"
    body += ("<p>Potent = IC50 &lt; 100 nM with QC passed. "
             "All values are synthetic and invented for this demo.</p>")
    body += "<h2>Median IC50 by target (QC-passed only)</h2><table><tr><th>Target</th><th>n</th><th>Median IC50 (nM)</th></tr>"
    body += rows([(r["target"], r["n"], r["median_ic50_nm"])
                  for r in report["median_ic50_by_target"]]) + "</table>"
    body += "<h2>Hit rate by assay type</h2><table><tr><th>Assay type</th><th>n</th><th>Potent</th><th>Hit rate</th></tr>"
    body += rows([(r["assay_type"], r["n"], r["potent"], r["hit_rate"])
                  for r in report["hit_rate_by_assay_type"]]) + "</table>"
    qc = report["qc_summary"]
    body += (f"<h2>QC summary</h2><p>{qc['qc_passed']} of {qc['results']} results "
             f"passed QC (rate {qc['qc_pass_rate']}).</p>")
    body += "<h2>Potent compounds</h2><table><tr><th>Result</th><th>Compound</th><th>Target</th><th>Assay type</th><th>IC50 (nM)</th></tr>"
    body += rows([(r["result_id"], r["compound"], r["target"], r["assay_type"], r["ic50_nm"])
                  for r in report["potent_compounds"]]) + "</table>"
    page = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Bioassay Dashboard</title>"
            "<style>body{font-family:sans-serif;margin:2em}"
            "table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px}"
            "th{background:#eee}</style></head><body>" + body + "</body></html>")
    with open(path, "w") as f:
        f.write(page)
