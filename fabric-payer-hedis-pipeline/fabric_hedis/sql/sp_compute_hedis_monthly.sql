-- Stored procedure: monthly HEDIS computation into gold_hedis_monthly.
-- Mirrors fabric_hedis/hedis.py compute_hedis. One row per measure per
-- month; re-running a month replaces its rows (idempotent).
-- Validated structurally by the test suite; not executed against a
-- Fabric workspace here.

CREATE OR ALTER PROCEDURE dbo.sp_compute_hedis_monthly
    @measurement_month CHAR(7)   -- e.g. '2026-10'
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @year INT = CAST(LEFT(@measurement_month, 4) AS INT);

    DELETE FROM dbo.gold_hedis_monthly
    WHERE measurement_month = @measurement_month;

    -- BCS: women 40-74 with a mammogram in the last 27 months.
    INSERT INTO dbo.gold_hedis_monthly
        (measure, measurement_month, denominator, numerator, rate)
    SELECT 'BCS', @measurement_month,
           COUNT(*),
           SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_screenings s
               WHERE s.member_id = m.member_id
                 AND s.screening_type = 'mammogram'
                 AND DATEDIFF(MONTH, s.screening_date,
                              EOMONTH(@measurement_month + '-01')) <= 27
           ) THEN 1 ELSE 0 END),
           CAST(SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_screenings s
               WHERE s.member_id = m.member_id
                 AND s.screening_type = 'mammogram'
                 AND DATEDIFF(MONTH, s.screening_date,
                              EOMONTH(@measurement_month + '-01')) <= 27
           ) THEN 1 ELSE 0 END) AS DECIMAL(10,4)) / NULLIF(COUNT(*), 0)
    FROM dbo.silver_members m
    WHERE m.sex = 'F' AND m.age BETWEEN 40 AND 74;

    -- COL: members 45-75 with a colonoscopy in 10 years or FIT this year.
    INSERT INTO dbo.gold_hedis_monthly
        (measure, measurement_month, denominator, numerator, rate)
    SELECT 'COL', @measurement_month,
           COUNT(*),
           SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_screenings s
               WHERE s.member_id = m.member_id
                 AND ((s.screening_type = 'colonoscopy'
                       AND DATEDIFF(YEAR, s.screening_date,
                                    @measurement_month + '-01') < 10)
                      OR (s.screening_type = 'FIT'
                          AND YEAR(s.screening_date) = @year))
           ) THEN 1 ELSE 0 END),
           CAST(SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_screenings s
               WHERE s.member_id = m.member_id
                 AND ((s.screening_type = 'colonoscopy'
                       AND DATEDIFF(YEAR, s.screening_date,
                                    @measurement_month + '-01') < 10)
                      OR (s.screening_type = 'FIT'
                          AND YEAR(s.screening_date) = @year))
           ) THEN 1 ELSE 0 END) AS DECIMAL(10,4)) / NULLIF(COUNT(*), 0)
    FROM dbo.silver_members m
    WHERE m.age BETWEEN 45 AND 75;

    -- CDC: diabetics 18-75 with HbA1c below 8.0 this year.
    INSERT INTO dbo.gold_hedis_monthly
        (measure, measurement_month, denominator, numerator, rate)
    SELECT 'CDC', @measurement_month,
           COUNT(*),
           SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'HbA1c'
                 AND YEAR(l.result_date) = @year
                 AND TRY_CAST(l.result AS DECIMAL(5,2)) < 8.0
           ) THEN 1 ELSE 0 END),
           CAST(SUM(CASE WHEN EXISTS (
               SELECT 1 FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'HbA1c'
                 AND YEAR(l.result_date) = @year
                 AND TRY_CAST(l.result AS DECIMAL(5,2)) < 8.0
           ) THEN 1 ELSE 0 END) AS DECIMAL(10,4)) / NULLIF(COUNT(*), 0)
    FROM dbo.silver_members m
    WHERE m.diabetes = 'Y' AND m.age BETWEEN 18 AND 75;

    -- CBP: hypertensives 18-85 whose latest BP this year is below 140/90.
    INSERT INTO dbo.gold_hedis_monthly
        (measure, measurement_month, denominator, numerator, rate)
    SELECT 'CBP', @measurement_month,
           COUNT(*),
           SUM(CASE WHEN (
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           ) LIKE '[0-9][0-9][0-9]/%' AND
           CAST(LEFT((
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           ), CHARINDEX('/', (
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           )) - 1) AS INT) < 140
           THEN 1 ELSE 0 END),
           CAST(SUM(CASE WHEN (
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           ) LIKE '[0-9][0-9][0-9]/%' AND
           CAST(LEFT((
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           ), CHARINDEX('/', (
               SELECT TOP 1 l.result FROM dbo.silver_labs l
               WHERE l.member_id = m.member_id AND l.test = 'BP'
                 AND YEAR(l.result_date) = @year
               ORDER BY l.result_date DESC
           )) - 1) AS INT) < 140
           THEN 1 ELSE 0 END) AS DECIMAL(10,4)) / NULLIF(COUNT(*), 0)
    FROM dbo.silver_members m
    WHERE m.hypertension = 'Y' AND m.age BETWEEN 18 AND 85;
END;
