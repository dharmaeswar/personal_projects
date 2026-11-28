-- Clinical EMR analytics measures — BigQuery Standard SQL.
-- Mirrors emr_analytics/measures.py over the same standardized tables.
-- Reference SQL for the analytics team: run it in BigQuery against the
-- emr_curated dataset (tables: encounters, vitals_std, labs_std,
-- medications_std, quarantine). Not executed by the local pipeline,
-- which runs the same logic on SQLite-free Python + CSV instead.
-- All source data in this project is synthetic and seeded.

WITH vitals_clean AS (
  SELECT encounter_id, vital_type
  FROM `emr_curated.vitals_std`
  WHERE quarantine_flag = FALSE
),
vitals_completeness AS (
  SELECT
    COUNTIF(
      EXISTS (SELECT 1 FROM vitals_clean v
              WHERE v.encounter_id = e.encounter_id
                AND v.vital_type = 'HEART_RATE')
      AND EXISTS (SELECT 1 FROM vitals_clean v
              WHERE v.encounter_id = e.encounter_id
                AND v.vital_type = 'BP_SYSTOLIC')
      AND EXISTS (SELECT 1 FROM vitals_clean v
              WHERE v.encounter_id = e.encounter_id
                AND v.vital_type = 'SPO2')
    ) AS complete_encounters,
    COUNT(*) AS encounters_total
  FROM `emr_curated.encounters` e
),
lab_turnaround AS (
  SELECT
    APPROX_QUANTILES(
      TIMESTAMP_DIFF(result_at, collected_at, MINUTE) / 60.0, 2
    )[OFFSET(1)] AS lab_turnaround_median_hours
  FROM `emr_curated.labs_std`
  WHERE quarantine_flag = FALSE
    AND result_at >= collected_at
),
med_reconciliation AS (
  SELECT
    COUNT(DISTINCT encounter_id) AS reconciled_encounters,
    (SELECT COUNT(*) FROM `emr_curated.encounters`) AS encounters_total
  FROM `emr_curated.medications_std`
  WHERE quarantine_flag = FALSE
),
data_quality AS (
  SELECT
    SUM(CASE WHEN quarantine_flag THEN 0 ELSE 1 END) AS clean_rows,
    COUNT(*) AS rows_total
  FROM (
    SELECT quarantine_flag FROM `emr_curated.vitals_std`
    UNION ALL SELECT quarantine_flag FROM `emr_curated.labs_std`
    UNION ALL SELECT quarantine_flag FROM `emr_curated.medications_std`
    UNION ALL SELECT quarantine_flag FROM `emr_curated.encounters`
  )
),
return_visits AS (
  SELECT
    COUNTIF(returned_within_30d) AS returning_patients,
    COUNT(*) AS patients_total
  FROM (
    SELECT
      patient_id,
      MAX(DATE_DIFF(next_date, encounter_date, DAY) <= 30) AS returned_within_30d
    FROM (
      SELECT
        patient_id,
        encounter_date,
        LEAD(encounter_date) OVER (
          PARTITION BY patient_id ORDER BY encounter_date
        ) AS next_date
      FROM `emr_curated.encounters`
    )
    GROUP BY patient_id
  )
)
SELECT
  (SELECT 100.0 * complete_encounters / encounters_total
     FROM vitals_completeness) AS vitals_completeness_pct,
  (SELECT lab_turnaround_median_hours FROM lab_turnaround) AS lab_turnaround_median_hours,
  (SELECT 100.0 * reconciled_encounters / encounters_total
     FROM med_reconciliation) AS med_reconciliation_pct,
  (SELECT 100.0 * clean_rows / rows_total FROM data_quality) AS data_quality_pass_rate_pct,
  (SELECT 100.0 * returning_patients / patients_total
     FROM return_visits) AS return_visit_rate_pct;
