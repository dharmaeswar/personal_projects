# AML Surveillance Data Pipeline

A Core Java ETL pipeline that builds surveillance data models and raises
rule-based AML alerts — built for the TD Bank AML Surveillance Tools
Engineer/Developer role (Req R_1494185, New York, Nov 2026).

**All data is synthetic and seeded.** No real bank, account, or transaction
data is used, and nothing here is a claim about any real institution or
customer. The detectors are screening rules that queue work for a human
analyst; they do not decide that money laundering happened.

## What it does

Four stages, one code path for the batch feed and the near-real-time
micro-batch feed:

1. **Ingest** (`Transaction`) — parses the upstream bank feed (core banking,
   wire, branch channel) into typed records with exact `BigDecimal` money
   arithmetic.
2. **Data quality** (`DataQuality`) — quarantines bad rows instead of
   silently dropping them: missing amount, non-positive amount, duplicate
   transaction id, wrong field count. Each quarantined row keeps its reason
   so an analyst can fix and re-feed it.
3. **Detectors** (`Detectors`) — rule-based surveillance over clean
   transactions, one alert per account per day per rule:
   - **STRUCTURING** (HIGH): 3+ cash deposits each under the $10,000 CTR
     reporting threshold in one day, totalling $25,000+.
   - **VELOCITY** (MEDIUM): 6+ transactions inside any 60-minute window.
   - **HIGH_RISK_CORRIDOR** (HIGH): 2+ wires to a high-risk jurisdiction
     in one day.
   - **ROUND_AMOUNT** (MEDIUM): 3+ payments of exactly $5,000 in one day.
4. **Surveillance data model** (`SurveillanceModel`) — one account-mart row
   per account: transaction count, total and largest amount, cash-deposit
   count/total, wire count/total, alert count.
5. **Vendor export** (`VendorExport`) — an Actimize-style pipe-delimited
   alert feed, the integration point a vendor surveillance platform would
   consume. This project does not run NICE Actimize itself; it produces the
   feed such a platform ingests.

## Runs locally, plain JDK only

No Maven, Gradle, Spark cluster, Databricks workspace, or third-party jars.
Java 17+ is the only requirement. The pipeline mirrors how the same logic
maps onto Spark/Databricks: the batch file is the daily batch job, the
second file is the near-real-time micro-batch, and the account mart is the
gold layer a Databricks lakehouse would hold.

```sh
./build.sh   # compiles, runs 32 tests, runs the demo (batch + micro-batch)
```

## Demo results (hand-verified)

- `data/transactions_batch1.csv`: 24 rows in, 21 clean, 3 quarantined,
  4 alerts — structuring ACCT-101 ($38,900 over 4 deposits), velocity
  ACCT-102 (8 payments in 46 minutes), high-risk corridor ACCT-103
  ($10,300 over 2 wires), round amounts ACCT-104 (3 x $5,000).
- `data/transactions_batch2.csv` (micro-batch): 10 rows in, 10 clean,
  0 quarantined, 2 alerts — structuring ACCT-106 ($29,400 over 3
  deposits), velocity ACCT-107 (6 payments in 31 minutes).
- Total: 34 rows, 31 clean, 3 quarantined, 6 alerts, 8 accounts in the
  mart. Outputs land in `output/`: `alerts.csv`, `account_mart.csv`,
  `quarantine.csv`, `vendor_actimize_feed.txt`.

## Tests

`src/test/java/aml/AmlPipelineTest.java` — 32 checks, plain JDK
assertions (`java -ea`), no test framework. Every expected value was
hand-computed from the input rows in the test (structuring total $38,900,
corridor total $10,300, round-amount total $15,000, mart totals 600/300),
including the negative cases: 2 deposits raise no structuring alert, a
$10,000 deposit breaks the under-threshold pattern, 5 transactions in an
hour raise no velocity alert.

## Honest limits

- No real Spark, Databricks, Hadoop, Kafka, Solace, or NICE Actimize
  runtime here — the code names the equivalents it mirrors and the README
  says so. Do not present this as production surveillance software.
- The high-risk country list (`XX`, `XY`) is a demo list for seeded data.
- Detectors are four fixed rules; there is no machine-learning scorer, no
  workflow engine, and no live vendor integration.
