-- usp_LoadClaims: load validated claims from staging into FactClaims.
-- @Mode = 'FULL' replaces the fact table; 'INCREMENTAL' loads only rows
-- with a FillDate after the last watermark (the latest LoadLog watermark).
-- Mirrors claims_etl/warehouse.py load_full / load_incremental.
USE Wellpartner;
GO

CREATE OR ALTER PROCEDURE dbo.usp_LoadClaims
    @Mode NVARCHAR(20),
    @LoadID INT
AS
BEGIN
    SET NOCOUNT ON;

    IF @Mode = 'FULL'
    BEGIN
        TRUNCATE TABLE dbo.FactClaims;
        INSERT INTO dbo.FactClaims
            (ClaimID, PatientID, NDC, Quantity, DaysSupply, FillDate,
             PharmacyID, PrescriberID, Amount, LoadID)
        SELECT ClaimID, PatientID, NDC, Quantity, DaysSupply, FillDate,
               PharmacyID, PrescriberID, Amount, @LoadID
        FROM dbo.StgClaims;
    END
    ELSE IF @Mode = 'INCREMENTAL'
    BEGIN
        DECLARE @Watermark DATE = (
            SELECT MAX(Watermark) FROM dbo.LoadLog WHERE Watermark IS NOT NULL
        );
        INSERT INTO dbo.FactClaims
            (ClaimID, PatientID, NDC, Quantity, DaysSupply, FillDate,
             PharmacyID, PrescriberID, Amount, LoadID)
        SELECT ClaimID, PatientID, NDC, Quantity, DaysSupply, FillDate,
               PharmacyID, PrescriberID, Amount, @LoadID
        FROM dbo.StgClaims
        WHERE (@Watermark IS NULL OR FillDate > @Watermark)
          AND ClaimID NOT IN (SELECT ClaimID FROM dbo.FactClaims);
    END
    ELSE
    BEGIN
        THROW 50001, 'usp_LoadClaims: @Mode must be FULL or INCREMENTAL.', 1;
    END
END;
GO
