-- Snowflake reconciliation for a home-health load.
-- Run after every load; all three checks must return 0 differences.
-- :RUN_ID is bound by the caller (the load's run id).

-- 1. Source rows must equal loaded + quarantined for the run.
SELECT 'source_vs_loaded_quarantined' AS CHECK_NAME,
       (SELECT SOURCE_ROWS FROM WH.LOAD_LOG WHERE RUN_ID = :RUN_ID)
       - ((SELECT COUNT(*) FROM WH.FACT_HOME_VISIT
            WHERE LOADED_AT >= (SELECT LOADED_AT FROM WH.LOAD_LOG
                                WHERE RUN_ID = :RUN_ID))
          + (SELECT COUNT(*) FROM WH.QUARANTINE WHERE RUN_ID = :RUN_ID))
       AS DIFFERENCE;

-- 2. No fact row may reference a non-current patient dimension row.
SELECT 'fact_to_non_current_patient' AS CHECK_NAME,
       COUNT(*) AS DIFFERENCE
FROM WH.FACT_HOME_VISIT f
JOIN WH.DIM_PATIENT p ON p.PATIENT_SK = f.PATIENT_SK
WHERE p.IS_CURRENT = FALSE;

-- 3. No duplicate natural keys (visit ids) in the fact table.
SELECT 'duplicate_visit_ids' AS CHECK_NAME,
       COUNT(*) AS DIFFERENCE
FROM (
    SELECT VISIT_ID FROM WH.FACT_HOME_VISIT
    GROUP BY VISIT_ID HAVING COUNT(*) > 1
);
