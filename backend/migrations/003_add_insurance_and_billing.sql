-- Migration 003: Add insurance system and billing fields
-- Date: 2026-03-07
-- Run this BEFORE restarting the backend after pulling this branch.

-- ── Insurance companies ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS insurance_companies (
    id           SERIAL PRIMARY KEY,
    plan_id      VARCHAR UNIQUE NOT NULL,
    plan_name    VARCHAR NOT NULL,
    bin_number   VARCHAR,
    pcn          VARCHAR,
    phone_number VARCHAR
);

-- ── Formulary (drug coverage per company) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS formulary (
    id                   SERIAL PRIMARY KEY,
    insurance_company_id INTEGER NOT NULL REFERENCES insurance_companies(id),
    drug_id              INTEGER NOT NULL REFERENCES drugs(id),
    tier                 INTEGER NOT NULL,       -- 1 Preferred Generic … 4 Specialty
    copay_per_30         NUMERIC(10,2) NOT NULL, -- patient cost for 30-day supply
    not_covered          BOOLEAN NOT NULL DEFAULT FALSE
);

-- ── Patient insurance cards ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patient_insurance (
    id                   SERIAL PRIMARY KEY,
    patient_id           INTEGER NOT NULL REFERENCES patients(id),
    insurance_company_id INTEGER NOT NULL REFERENCES insurance_companies(id),
    member_id            VARCHAR NOT NULL,
    group_number         VARCHAR,
    is_primary           BOOLEAN NOT NULL DEFAULT TRUE,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE
);

-- ── Billing columns on refills ─────────────────────────────────────────────
ALTER TABLE refills
    ADD COLUMN IF NOT EXISTS insurance_id   INTEGER REFERENCES patient_insurance(id),
    ADD COLUMN IF NOT EXISTS copay_amount   NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS insurance_paid NUMERIC(10,2);

-- ── Billing columns on refill_hist ────────────────────────────────────────
ALTER TABLE refill_hist
    ADD COLUMN IF NOT EXISTS insurance_id   INTEGER REFERENCES patient_insurance(id),
    ADD COLUMN IF NOT EXISTS copay_amount   NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS insurance_paid NUMERIC(10,2);

-- ── Specialty column on prescribers ───────────────────────────────────────
ALTER TABLE prescribers
    ADD COLUMN IF NOT EXISTS specialty VARCHAR;
