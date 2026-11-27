-- PostgreSQL schema for mortgage loan servicing.
-- The demo service runs on an in-memory store; this DDL is the deployment schema
-- the JPA repository would target. Amounts are NUMERIC(19,2) — never float/double.
-- Indexes are chosen for the queries the service actually runs.

CREATE TABLE IF NOT EXISTS loans (
    id                  UUID PRIMARY KEY,
    borrower_name       TEXT NOT NULL,
    original_principal  NUMERIC(19,2) NOT NULL CHECK (original_principal > 0),
    remaining_principal NUMERIC(19,2) NOT NULL CHECK (remaining_principal >= 0),
    annual_rate_pct     NUMERIC(7,4) NOT NULL CHECK (annual_rate_pct >= 0),
    term_months         INT NOT NULL CHECK (term_months >= 12),
    start_date          DATE NOT NULL,
    escrow_monthly      NUMERIC(19,2) NOT NULL DEFAULT 0 CHECK (escrow_monthly >= 0),
    escrow_balance      NUMERIC(19,2) NOT NULL DEFAULT 0 CHECK (escrow_balance >= 0),
    last_payment_date   DATE,
    status              TEXT NOT NULL DEFAULT 'CURRENT'
                        CHECK (status IN ('CURRENT', 'DELINQUENT', 'PAID_OFF')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id                        UUID PRIMARY KEY,
    loan_id                   UUID NOT NULL REFERENCES loans (id),
    amount                    NUMERIC(19,2) NOT NULL CHECK (amount > 0),
    payment_date              DATE NOT NULL,
    principal_portion         NUMERIC(19,2) NOT NULL,
    interest_portion          NUMERIC(19,2) NOT NULL,
    escrow_portion            NUMERIC(19,2) NOT NULL,
    idempotency_key           TEXT UNIQUE,
    remaining_principal_after NUMERIC(19,2) NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Payment history for one loan, newest first (GET /api/loans/{id}/payments).
CREATE INDEX IF NOT EXISTS idx_payments_loan_date
    ON payments (loan_id, payment_date DESC);

-- Idempotency replay lookup (POST /api/loans/{id}/payments with a key).
CREATE INDEX IF NOT EXISTS idx_payments_idempotency_key
    ON payments (idempotency_key) WHERE idempotency_key IS NOT NULL;

-- Delinquency sweep: loans with no payment in the last 30 days.
CREATE INDEX IF NOT EXISTS idx_loans_delinquency
    ON loans (status, last_payment_date) WHERE status <> 'PAID_OFF';

-- Servicing queue: loans ordered by next payment due (start + months paid).
CREATE INDEX IF NOT EXISTS idx_loans_start_date ON loans (start_date);
