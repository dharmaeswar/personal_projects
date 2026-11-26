-- Stored procedure: bronze -> silver claim load (Fabric Warehouse).
-- Mirrors fabric_hedis/medallion.py promote_to_silver: dedupe keeps the
-- latest copy of each claim_id, validates each row, and quarantines
-- failures with every rule that caught them. Validated structurally by
-- the test suite; not executed against a Fabric workspace here.

CREATE OR ALTER PROCEDURE dbo.sp_load_silver_claims
AS
BEGIN
    SET NOCOUNT ON;

    -- Dedupe: latest copy of each claim_id wins (ingest order).
    WITH ranked AS (
        SELECT c.*,
               ROW_NUMBER() OVER (PARTITION BY claim_id
                                  ORDER BY ingested_at DESC) AS rn
        FROM dbo.bronze_claims AS c
    )
    SELECT * INTO #latest FROM ranked WHERE rn = 1;

    -- Quarantine every row that fails any rule, naming each rule.
    INSERT INTO dbo.quarantine (source_table, record_id, reason, payload)
    SELECT 'bronze_claims', claim_id,
           STRING_AGG(reason, ';'),
           CONCAT(claim_id, '|', member_id, '|', service_date)
    FROM (
        SELECT claim_id, member_id, service_date,
               'unknown_member_id' AS reason
        FROM #latest
        WHERE member_id NOT IN (SELECT member_id FROM dbo.silver_members)
        UNION ALL
        SELECT claim_id, member_id, service_date,
               'negative_paid_amount'
        FROM #latest WHERE paid_amount < 0
        UNION ALL
        SELECT claim_id, member_id, service_date,
               'service_date_out_of_range'
        FROM #latest
        WHERE service_date < '2026-01-01' OR service_date > '2026-10-31'
        UNION ALL
        SELECT claim_id, member_id, service_date,
               'paid_amount_mismatch'
        FROM #latest
        WHERE ABS(paid_amount - (billed_amount - adjustment)) > 0.01
    ) AS problems
    GROUP BY claim_id, member_id, service_date;

    -- Load the clean rows; MERGE keeps the load idempotent on claim_id.
    MERGE INTO dbo.silver_claims AS target
    USING (
        SELECT * FROM #latest
        WHERE claim_id NOT IN (SELECT record_id FROM dbo.quarantine)
    ) AS src
    ON target.claim_id = src.claim_id
    WHEN MATCHED THEN UPDATE SET
        target.member_id = src.member_id,
        target.service_date = src.service_date,
        target.diag_code = src.diag_code,
        target.procedure_code = src.procedure_code,
        target.billed_amount = src.billed_amount,
        target.adjustment = src.adjustment,
        target.paid_amount = src.paid_amount,
        target.source_file = src.source_file
    WHEN NOT MATCHED THEN INSERT
        (claim_id, member_id, service_date, diag_code, procedure_code,
         billed_amount, adjustment, paid_amount, source_file)
    VALUES
        (src.claim_id, src.member_id, src.service_date, src.diag_code,
         src.procedure_code, src.billed_amount, src.adjustment,
         src.paid_amount, src.source_file);

    DROP TABLE #latest;
END;
