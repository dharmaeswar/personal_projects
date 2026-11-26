-- Scalar function: is a member eligible for a HEDIS measure?
-- Used by ad-hoc checks and by the monthly procedure's WHERE clauses.
-- Validated structurally by the test suite; not executed against a
-- Fabric workspace here.

CREATE OR ALTER FUNCTION dbo.fn_hedis_eligible (
    @measure      VARCHAR(10),
    @sex          CHAR(1),
    @age          INT,
    @diabetes     CHAR(1),
    @hypertension CHAR(1)
)
RETURNS BIT
AS
BEGIN
    RETURN CASE
        WHEN @measure = 'BCS'
             AND @sex = 'F' AND @age BETWEEN 40 AND 74 THEN 1
        WHEN @measure = 'COL'
             AND @age BETWEEN 45 AND 75 THEN 1
        WHEN @measure = 'CDC'
             AND @diabetes = 'Y' AND @age BETWEEN 18 AND 75 THEN 1
        WHEN @measure = 'CBP'
             AND @hypertension = 'Y' AND @age BETWEEN 18 AND 85 THEN 1
        ELSE 0
    END;
END;
