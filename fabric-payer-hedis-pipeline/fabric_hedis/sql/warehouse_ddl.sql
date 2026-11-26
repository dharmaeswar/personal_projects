-- Fabric Warehouse DDL for the payer file exchange.
-- Target: Microsoft Fabric Warehouse (T-SQL). This file is validated
-- structurally by the test suite; it is NOT executed against a Fabric
-- workspace here. The local demo runs the same shapes in SQLite
-- (see fabric_hedis/medallion.py).

CREATE TABLE dbo.bronze_claims (
    claim_id        VARCHAR(20)  NOT NULL,
    member_id       VARCHAR(20)  NOT NULL,
    service_date    DATE         NOT NULL,
    diag_code       VARCHAR(10)  NOT NULL,
    procedure_code  VARCHAR(10)  NOT NULL,
    billed_amount   DECIMAL(12,2) NOT NULL,
    adjustment      DECIMAL(12,2) NOT NULL,
    paid_amount     DECIMAL(12,2) NOT NULL,
    source_file     VARCHAR(100) NOT NULL,
    ingested_at     DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.silver_claims (
    claim_id        VARCHAR(20)  NOT NULL PRIMARY KEY,
    member_id       VARCHAR(20)  NOT NULL,
    service_date    DATE         NOT NULL,
    diag_code       VARCHAR(10)  NOT NULL,
    procedure_code  VARCHAR(10)  NOT NULL,
    billed_amount   DECIMAL(12,2) NOT NULL,
    adjustment      DECIMAL(12,2) NOT NULL,
    paid_amount     DECIMAL(12,2) NOT NULL,
    source_file     VARCHAR(100) NOT NULL
);

CREATE TABLE dbo.quarantine (
    source_table    VARCHAR(50)  NOT NULL,
    record_id       VARCHAR(20)  NOT NULL,
    reason          VARCHAR(500) NOT NULL,
    payload         VARCHAR(MAX) NOT NULL,
    quarantined_at  DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.gold_hedis_monthly (
    measure           VARCHAR(10)  NOT NULL,
    measurement_month CHAR(7)      NOT NULL,
    denominator       INT          NOT NULL,
    numerator         INT          NOT NULL,
    rate              DECIMAL(6,4) NOT NULL,
    PRIMARY KEY (measure, measurement_month)
);

CREATE TABLE dbo.delta_log (
    version         INT IDENTITY(1,1) PRIMARY KEY,
    table_name      VARCHAR(50)  NOT NULL,
    operation       VARCHAR(20)  NOT NULL,
    rows_affected   INT          NOT NULL,
    logged_at       DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Performance: the monthly HEDIS query filters silver_claims by
-- service_date and joins on member_id; keep both indexed.
CREATE NONCLUSTERED INDEX IX_silver_claims_service_date
    ON dbo.silver_claims (service_date);
CREATE NONCLUSTERED INDEX IX_silver_claims_member_id
    ON dbo.silver_claims (member_id);
