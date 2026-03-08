-- Migration: Renumber prescription IDs to 7-digit format (17xxxxx)
-- New ID = 1700000 + current ID
-- Example: ID 1 -> 1700001, ID 42 -> 1700042

BEGIN;

-- Disable FK checks so we can update PK and FKs independently
SET session_replication_role = replica;

-- Update foreign keys in refills and refill_hist first
UPDATE refills    SET prescription_id = 1700000 + prescription_id;
UPDATE refill_hist SET prescription_id = 1700000 + prescription_id;

-- Update the primary key on prescriptions
UPDATE prescriptions SET id = 1700000 + id;

-- Advance the sequence past the new max ID
SELECT setval('prescriptions_id_seq', (SELECT MAX(id) FROM prescriptions));

-- Re-enable FK checks
SET session_replication_role = DEFAULT;

COMMIT;
