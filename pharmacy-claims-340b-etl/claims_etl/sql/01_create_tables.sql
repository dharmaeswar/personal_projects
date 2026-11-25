-- Wellpartner 340B warehouse tables (SQL Server / T-SQL).
-- Mirrors the SQLite schema in claims_etl/warehouse.py.
USE Wellpartner;
GO

CREATE TABLE dbo.DimPatient (
    PatientID   CHAR(10)     NOT NULL PRIMARY KEY,
    PatientName NVARCHAR(20) NOT NULL,
    Eligible    CHAR(1)      NOT NULL CHECK (Eligible IN ('Y', 'N')),
    StartDate   DATE         NOT NULL,
    EndDate     DATE         NOT NULL
);
GO

CREATE TABLE dbo.DimDrug (
    NDC       CHAR(11)       NOT NULL PRIMARY KEY,
    DrugName  NVARCHAR(100)  NOT NULL,
    UnitPrice DECIMAL(10, 2) NOT NULL
);
GO

CREATE TABLE dbo.FactClaims (
    ClaimID      NVARCHAR(20)   NOT NULL PRIMARY KEY,
    PatientID    CHAR(10)       NOT NULL,
    NDC          CHAR(11)       NOT NULL,
    Quantity     INT            NOT NULL,
    DaysSupply   INT            NOT NULL,
    FillDate     DATE           NOT NULL,
    PharmacyID   NVARCHAR(10)   NOT NULL,
    PrescriberID NVARCHAR(10)   NOT NULL,
    Amount       DECIMAL(10, 2) NOT NULL,
    LoadID       INT            NOT NULL,
    CONSTRAINT FK_FactClaims_Patient FOREIGN KEY (PatientID)
        REFERENCES dbo.DimPatient (PatientID),
    CONSTRAINT FK_FactClaims_Drug FOREIGN KEY (NDC)
        REFERENCES dbo.DimDrug (NDC)
);
GO

CREATE TABLE dbo.LoadLog (
    LoadID          INT IDENTITY(1, 1) PRIMARY KEY,
    Mode            NVARCHAR(20) NOT NULL,
    SourceRows      INT NOT NULL,
    LoadedRows      INT NOT NULL,
    QuarantinedRows INT NOT NULL,
    Watermark       DATE NULL,
    LoadedAt        DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE TABLE dbo.Quarantine (
    ClaimID    NVARCHAR(20)   NOT NULL,
    LoadID     INT            NOT NULL,
    Violations NVARCHAR(MAX)  NOT NULL,
    CONSTRAINT PK_Quarantine PRIMARY KEY (ClaimID, LoadID)
);
GO
