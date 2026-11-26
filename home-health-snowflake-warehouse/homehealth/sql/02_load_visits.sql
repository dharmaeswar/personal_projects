-- Snowflake MERGE load for validated home-health visits.
-- Source: WH.STG_VISITS (validated staging table, one row per visit).
-- The MERGE is idempotent on VISIT_ID: a re-run inserts nothing new.
-- The watermark table tracks the newest loaded visit date so the next
-- incremental run only processes newer rows.

MERGE INTO WH.FACT_HOME_VISIT T
USING (
    SELECT v.VISIT_ID,
           p.PATIENT_SK,
           c.CLINICIAN_SK,
           d.DATE_SK,
           v.DURATION_MIN,
           v.ASSESSMENT_SCORE,
           v.SOURCE,
           v.SCHEMA_VERSION
    FROM WH.STG_VISITS v
    JOIN WH.DIM_PATIENT p
      ON p.PATIENT_KEY = v.PATIENT_KEY AND p.IS_CURRENT = TRUE
    JOIN WH.DIM_CLINICIAN c
      ON c.CLINICIAN_ID = v.CLINICIAN_ID
    JOIN WH.DIM_DATE d
      ON d.DATE_SK = v.VISIT_DATE
    WHERE v.VISIT_DATE > COALESCE(
        (SELECT LAST_VISIT_DATE FROM WH.WATERMARK WHERE ID = 1),
        DATE '1900-01-01')
) S
ON T.VISIT_ID = S.VISIT_ID
WHEN NOT MATCHED THEN INSERT (
    VISIT_ID, PATIENT_SK, CLINICIAN_SK, DATE_SK,
    DURATION_MIN, ASSESSMENT_SCORE, SOURCE, SCHEMA_VERSION, LOADED_AT
) VALUES (
    S.VISIT_ID, S.PATIENT_SK, S.CLINICIAN_SK, S.DATE_SK,
    S.DURATION_MIN, S.ASSESSMENT_SCORE, S.SOURCE, S.SCHEMA_VERSION,
    CURRENT_TIMESTAMP()
);

UPDATE WH.WATERMARK
SET LAST_VISIT_DATE = (SELECT MAX(VISIT_DATE) FROM WH.FACT_HOME_VISIT)
WHERE ID = 1;
