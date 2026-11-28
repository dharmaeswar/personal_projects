"""Run the bioassay ETL: validate -> SQLite warehouse -> graph -> dashboard."""

import json

from kg_rag.bioassay import (BIOASSAY_RESULTS, add_bioassay_edges,
                             build_dashboard, clean_results, load_sqlite,
                             report_queries, write_report_csv)
from kg_rag.corpus import DOCUMENTS
from kg_rag.graph import KnowledgeGraph


def main():
    clean, rejected = clean_results(BIOASSAY_RESULTS)
    print(f"Rows: {len(BIOASSAY_RESULTS)} seeded, {len(clean)} clean, "
          f"{len(rejected)} rejected")
    for rej in rejected:
        print(f"  rejected {rej['result_id']}: {'; '.join(rej['reasons'])}")
    conn = load_sqlite(clean, "bioassay.db")
    report = report_queries(conn, clean)
    conn.close()
    graph = KnowledgeGraph.build(DOCUMENTS)
    assays_added, edges_added = add_bioassay_edges(graph, clean)
    print(f"Graph: {assays_added} assays, {edges_added} bioassay edges added")
    print("Graph:", json.dumps(graph.summary()))
    with open("bioassay_graph_summary.json", "w") as f:
        json.dump(graph.summary(), f, indent=2)
    write_report_csv(report, "bioassay_report.csv")
    build_dashboard(report, "dashboard.html")
    print("Wrote bioassay.db, bioassay_report.csv, dashboard.html, "
          "bioassay_graph_summary.json")
    print("Median IC50 by target:", json.dumps(report["median_ic50_by_target"]))
    print("Hit rate by assay type:", json.dumps(report["hit_rate_by_assay_type"]))
    print("QC:", json.dumps(report["qc_summary"]))
    print(f"Potent compounds: {len(report['potent_compounds'])}")


if __name__ == "__main__":
    main()
