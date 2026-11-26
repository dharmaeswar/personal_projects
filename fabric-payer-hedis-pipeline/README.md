# Fabric Payer File Exchange & HEDIS Pipeline

A portfolio project for a Senior Data Engineer role (Microsoft Fabric /
Azure). It builds the pipeline the JD asks for over synthetic healthcare
payer data: receive monthly payer files over an SFTP-style exchange,
validate format and content before anything lands downstream, run the
round-trip flow of files to and from a third-party vendor, load a
Fabric medallion lakehouse (bronze → silver → gold), compute monthly
HEDIS quality measures, monitor pipeline health, and publish a Power BI
semantic model — orchestrated as a monthly run with CI/CD in Azure
DevOps.

**All data is synthetic and seeded (seed 42).** No real member, patient,
claim, or PHI data is used, and nothing here is a claim about any real
insurer, payer, vendor, or person.

## Runs locally, without Fabric, Azure, or an SFTP server

Microsoft Fabric, Azure, and SFTP are not installed here, so the pipeline
runs locally with SQLite + the Python standard library. It does **not**
pretend a cloud run happened. The `sftp/` folders stand in for the SFTP
server (inbound payer drop, outbound vendor files, vendor returns), the
SQLite database stands in for the Fabric Lakehouse + Warehouse, and the
SQL in `fabric_hedis/sql/` is the production T-SQL for the same steps,
validated structurally by the test suite. `requirements.txt` lists only
pytest.

## Fabric / Azure mapping

| This project (local) | Microsoft Fabric / Azure equivalent |
|---|---|
| `sftp/inbound/` + manifest.json | SFTP payer file drop; manifest = expected rows + SHA-256 |
| `validate_file` — header, checksum, row count | ADF Copy activity validation + data-flow assertions |
| `bronze_*` tables + `delta_log` | Fabric Lakehouse bronze Delta Lake tables |
| `promote_to_silver` — dedupe + rules + quarantine | Fabric Notebook / Dataflow Gen2; Delta Lake MERGE |
| `silver_*` tables | Fabric Lakehouse silver Delta Lake tables |
| `gold_hedis_monthly` | Fabric Warehouse gold table / Lakehouse gold Delta table |
| `fabric_hedis/sql/*.sql` | Fabric Warehouse stored procedures + function |
| `run_monthly` step runner with retry + `run_log` | ADF pipeline (Notebook + Stored Procedure activities, retry policy) |
| `powerbi_semantic_model.json` | Power BI dataset: tables, DAX measures, relationships, RLS role |
| `azure-pipelines.yml` | Azure DevOps CI/CD (test → demo run → publish report) |

## What it validates

- **Manifest**: every inbound file must match its SHA-256, header, and
  row count before it is read; one bad file stops the run.
- **Dedup**: window-function rule keeps the latest copy of each
  `claim_id` (the late duplicate of C00001 carries a changed paid amount).
- **Content rules**: unknown `member_id`, negative paid amount, service
  date outside 2026-01-01 – 2026-10-31, unknown `diag_code`, and the
  arithmetic rule `paid_amount = billed_amount - adjustment` (±0.01).
- **Quarantine**: every failing row is quarantined with every rule that
  caught it; nothing is silently dropped.
- **HEDIS**: BCS, COL, CDC, CBP denominators/numerators from silver
  members, labs, and screenings with documented eligibility rules.
- **Reconciliation**: bronze = silver + quarantined + duplicates removed.
- **Vendor round-trip**: the gold HEDIS extract is sent with a manifest
  and the vendor acknowledgement is checked row-for-row.
- **Health**: quarantine rate over 5%, row-count swing over 20% vs last
  month, or any failed step raises an alert.

One honest wrinkle the checks caught: the late duplicate copy of C00001
carries `paid_amount` $1.00 higher than the original, so after dedup
keeps the latest copy, that row fails the arithmetic check and lands in
quarantine as `paid_amount_mismatch` (6 total: 1 duplicate + 5 planted).
A late correction that changes a value is a real data-quality break, and
the pipeline treats it as one instead of silently keeping it.

## Results (real run, Nov 26, 2026)

```
bronze claims: 186 (duplicates removed: 1)
silver claims: 179; quarantined: 6
BCS: 8/17 = 47.1%
COL: 31/31 = 100.0%
CDC: 10/20 = 50.0%
CBP: 20/30 = 66.7%
vendor round-trip: 4 accepted, 0 rejected
HEALTHY: no alerts
```

- Raw claims: **186** (180 clean + 6 planted defects)
- Duplicates removed by window dedup: **1**
- Quarantined rows: **6** — paid_amount_mismatch 2, negative_paid_amount 1,
  unknown_member_id 1, service_date_out_of_range 1, unknown_diag_code 1
- Cleansed claims: **179**; members **60**; reconciliation PASS
- HEDIS denominators: BCS 17, COL 31, CDC 20, CBP 30
- Re-running the month is idempotent (bronze is replaced, gold rows for
  the month are replaced, vendor file rewritten with the same content).

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py            # monthly run for 2026-10 into ./work
python -m pytest -q               # 29 tests
```

`run_pipeline.py` writes `work/hedis_report.json` + `hedis_report.txt`,
`work/powerbi_semantic_model.json`, the vendor extract under
`work/sftp/outbound/`, and the warehouse SQLite file
`work/fabric_warehouse.db` (bronze/silver/gold, quarantine, delta_log,
run_log, run_stats).

## Honest limits

All data is synthetic and seeded; nothing describes real Humana, payer,
or vendor data. SQLite stands in for Fabric Lakehouse/Warehouse and
Delta Lake — the T-SQL in `fabric_hedis/sql/` is validated structurally,
not executed against Fabric. The SFTP exchange is local folders, not a
real SFTP server; the vendor acknowledgement is simulated in-process,
not a live vendor integration. The Power BI model is a JSON export, not
a published dataset. FHIR/HL7 parsing is not implemented — the inbound
feeds are flat CSVs, as the JD's file-transfer work describes.
Demonstrated on 60 members and 186 claims, not at production scale.
