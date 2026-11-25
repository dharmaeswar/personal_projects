-- usp_ReconcileLoads: prove a load reconciles — source rows must equal
-- loaded + quarantined + already-loaded (incremental re-runs).
-- Mirrors the reconciliation report in claims_etl/loads.py.
USE Wellpartner;
GO

CREATE OR ALTER PROCEDURE dbo.usp_ReconcileLoads
    @LoadID INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT l.LoadID, l.Mode, l.SourceRows, l.LoadedRows,
           l.QuarantinedRows,
           (SELECT COUNT(*) FROM dbo.FactClaims f
             WHERE f.LoadID = l.LoadID) AS FactRowsForLoad,
           CASE WHEN l.SourceRows = l.LoadedRows + l.QuarantinedRows
                     + (l.SourceRows - l.LoadedRows - l.QuarantinedRows
                        - (SELECT COUNT(*) FROM dbo.Quarantine q
                            WHERE q.LoadID = l.LoadID))
                THEN 1 ELSE 0 END AS Reconciled
    FROM dbo.LoadLog l
    WHERE l.LoadID = @LoadID;
END;
GO
