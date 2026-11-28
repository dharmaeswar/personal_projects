"""Tests for the bioassay ETL, SQL warehouse, graph extension and dashboard."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kg_rag.bioassay import (BIOASSAY_RESULTS, add_bioassay_edges,
                             build_dashboard, clean_results, load_sqlite,
                             report_queries, write_report_csv)
from kg_rag.corpus import DOCUMENTS
from kg_rag.graph import KnowledgeGraph


def test_dirty_rows_rejected():
    clean, rejected = clean_results(BIOASSAY_RESULTS)
    assert len(BIOASSAY_RESULTS) == 16
    assert len(clean) == 14
    assert {r["result_id"] for r in rejected} == {"BA-015", "BA-016"}
    reasons = {r["result_id"]: r["reasons"] for r in rejected}
    assert any("ic50_nm" in r for r in reasons["BA-015"])
    assert any("replicates" in r for r in reasons["BA-016"])


def test_sqlite_tables_and_potent_view(tmp_path):
    clean, _ = clean_results(BIOASSAY_RESULTS)
    conn = load_sqlite(clean, str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"assays", "bioassay_results"} <= tables
    views = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    assert "v_potent_compounds" in views
    potent = conn.execute("SELECT result_id FROM v_potent_compounds").fetchall()
    potent_ids = {r[0] for r in potent}
    # Potent (<100 nM) and QC-passed only: BA-013/BA-014 fail QC, BA-015/BA-016 rejected.
    assert potent_ids == {"BA-001", "BA-002", "BA-003", "BA-004", "BA-007",
                          "BA-009", "BA-010"}
    joined = conn.execute(
        "SELECT COUNT(*) FROM bioassay_results r JOIN assays a "
        "ON r.assay_id = a.assay_id").fetchone()[0]
    assert joined == 14
    conn.close()


def test_report_medians_and_hit_rates(tmp_path):
    clean, _ = clean_results(BIOASSAY_RESULTS)
    conn = load_sqlite(clean, str(tmp_path / "test.db"))
    report = report_queries(conn, clean)
    conn.close()
    medians = {r["target"]: r["median_ic50_nm"]
               for r in report["median_ic50_by_target"]}
    assert medians["EGFR"] == 10.2  # median of 8.5, 12.0
    assert medians["BRAF"] == 3.6  # median of 3.2, 4.1
    assert medians["BRCA1"] == 48.5  # median of 42.0, 55.0 (QC-failed rows excluded)
    assert report["qc_summary"] == {"results": 14, "qc_passed": 12,
                                    "qc_pass_rate": 0.857}
    hits = {r["assay_type"]: r for r in report["hit_rate_by_assay_type"]}
    assert hits["Enzymatic inhibition"]["potent"] == 4
    assert hits["Cell viability"]["potent"] == 0


def test_graph_extension_links_compound_to_target():
    clean, _ = clean_results(BIOASSAY_RESULTS)
    graph = KnowledgeGraph.build(DOCUMENTS)
    before = graph.summary()
    assays_added, edges_added = add_bioassay_edges(graph, clean)
    assert assays_added == 7
    assert edges_added == 14
    after = graph.summary()
    assert after["nodes_by_type"]["Assay"] == 7
    assert after["edges_by_relation"]["TESTED_IN"] == 7
    assert after["edges_by_relation"]["MEASURES"] == 7
    assert after["nodes"] == before["nodes"] + 7
    neighbours, _ = graph.neighbours("Olaparib", hops=2)
    assert "BRCA1" in neighbours  # Olaparib -TESTED_IN-> ASY-101 -MEASURES-> BRCA1


def test_dashboard_and_csv(tmp_path):
    clean, _ = clean_results(BIOASSAY_RESULTS)
    conn = load_sqlite(clean, str(tmp_path / "test.db"))
    report = report_queries(conn, clean)
    conn.close()
    dash = tmp_path / "dashboard.html"
    build_dashboard(report, str(dash))
    text = dash.read_text()
    for token in ["EGFR", "BRAF", "Median IC50", "Hit rate", "Osimertinib"]:
        assert token in text
    csv_path = tmp_path / "report.csv"
    write_report_csv(report, str(csv_path))
    lines = csv_path.read_text().splitlines()
    assert lines[0] == "result_id,compound,target,assay_type,ic50_nm"
    assert len(lines) == 1 + len(report["potent_compounds"]) == 8
