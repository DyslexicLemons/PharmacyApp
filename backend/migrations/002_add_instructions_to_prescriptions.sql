-- Migration: Add instructions field to prescriptions table
-- Date: 2026-03-07

ALTER TABLE prescriptions
ADD COLUMN IF NOT EXISTS instructions VARCHAR;
