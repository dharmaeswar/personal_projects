-- usp_Validate340B: apply the 340B validation rules to staging rows and
-- write every failing claim to dbo.Quarantine with the rules it broke.
-- Mirrors claims_etl/validate.py (R1 eligibility, R2 NDC format,
-- R3 utilisation bounds, R4 amount vs pricing, R5 duplicates,
-- R6 TPA capture).
USE Wellpartner;
GO

CREATE OR ALTER PROCEDURE dbo.usp_Validate340B
    @LoadID INT
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.Quarantine (ClaimID, LoadID, Violations)
    SELECT s.ClaimID, @LoadID,
           STRING_AGG(v.Violation, '; ') WITHIN GROUP (ORDER BY v.Violation)
    FROM dbo.StgClaims s
    CROSS APPLY (
        VALUES
        (CASE WHEN p.PatientID IS NULL OR p.Eligible <> 'Y'
               OR s.FillDate < p.StartDate OR s.FillDate > p.EndDate
              THEN 'patient not 340B-eligible on fill date' END),
        (CASE WHEN LEN(s.NDC) <> 11 OR s.NDC LIKE '%[^0-9]%'
              THEN 'NDC is not an 11-digit code' END),
        (CASE WHEN s.Quantity <= 0 OR s.DaysSupply < 1 OR s.DaysSupply > 90
               OR s.Quantity > s.DaysSupply * 4
              THEN 'quantity / days-supply outside 340B bounds' END),
        (CASE WHEN d.NDC IS NULL
              THEN 'no pricing record for NDC'
              WHEN ABS(s.Amount - s.Quantity * d.UnitPrice) > 0.01
              THEN 'amount does not match quantity x unit price' END),
        (CASE WHEN EXISTS (SELECT 1 FROM dbo.StgClaims s2
                           WHERE s2.ClaimID = s.ClaimID
                             AND s2.RowID < s.RowID)
              THEN 'duplicate claim_id in batch' END),
        (CASE WHEN NOT EXISTS (SELECT 1 FROM dbo.StgTpaCaptures t
                               WHERE t.ClaimID = s.ClaimID)
              THEN 'no 340B TPA capture for claim' END)
    ) AS v (Violation)
    LEFT JOIN dbo.DimPatient p ON p.PatientID = s.PatientID
    LEFT JOIN dbo.DimDrug d ON d.NDC = s.NDC
    WHERE v.Violation IS NOT NULL
    GROUP BY s.ClaimID;
END;
GO
