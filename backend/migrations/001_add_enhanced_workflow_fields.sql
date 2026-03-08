-- Migration: Add enhanced workflow fields to support READY, HOLD, REJECTED states
-- Date: 2026-01-10

-- Add new columns to refills table
ALTER TABLE refills
ADD COLUMN IF NOT EXISTS bin_number INTEGER,
ADD COLUMN IF NOT EXISTS rejected_by VARCHAR,
ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR,
ADD COLUMN IF NOT EXISTS rejection_date DATE,
ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'manual';

-- Add description column to drugs table
ALTER TABLE drugs
ADD COLUMN IF NOT EXISTS description VARCHAR;

-- Update existing refills to have source='manual' where NULL
UPDATE refills SET source = 'manual' WHERE source IS NULL;

-- Note: RxState enum values will be updated automatically by SQLAlchemy
-- when the app restarts with the new model definitions
