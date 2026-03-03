-- ============================================
-- CHECKPOINT COLUMN SWAP SCRIPT
-- ============================================
-- WARNING: This script will DROP the old BYTEA columns
-- ONLY RUN AFTER:
--   1. Verifying migration completion (verify_migration.sql)
--   2. Taking a database backup
--   3. Testing application with _jsonb columns
-- ============================================

-- STEP 0: Final verification check (must return 0)
DO $$
DECLARE
    unmigrated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unmigrated_count
    FROM checkpoints
    WHERE checkpoint IS NOT NULL AND checkpoint_jsonb IS NULL;
    
    IF unmigrated_count > 0 THEN
        RAISE EXCEPTION 'MIGRATION INCOMPLETE: % rows still have checkpoint but no checkpoint_jsonb', unmigrated_count;
    END IF;
    
    RAISE NOTICE 'Verification passed: All rows migrated';
END $$;

-- STEP 1: Drop old BYTEA columns
-- This is irreversible - make sure you have a backup!
ALTER TABLE checkpoints
    DROP COLUMN IF EXISTS checkpoint CASCADE,
    DROP COLUMN IF EXISTS metadata CASCADE;

-- STEP 2: Rename JSONB columns to original names
ALTER TABLE checkpoints
    RENAME COLUMN checkpoint_jsonb TO checkpoint;

ALTER TABLE checkpoints
    RENAME COLUMN metadata_jsonb TO metadata;

-- STEP 3: Recreate indexes with correct names
-- Drop the temporary index
DROP INDEX IF EXISTS idx_checkpoints_jsonb_null;

-- Create standard indexes for JSONB columns (optional, for performance)
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id 
    ON checkpoints (thread_id);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ns_id 
    ON checkpoints (thread_id, checkpoint_ns, checkpoint_id);

-- Optionally create GIN index for JSONB querying (if needed for performance)
-- CREATE INDEX IF NOT EXISTS idx_checkpoints_checkpoint_gin 
--     ON checkpoints USING GIN (checkpoint);

-- STEP 4: Verify column swap
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'checkpoints'
  AND column_name IN ('checkpoint', 'metadata')
ORDER BY column_name;

-- STEP 5: Verify data is still accessible
SELECT 
    thread_id,
    checkpoint_ns,
    checkpoint_id,
    jsonb_typeof(checkpoint) as checkpoint_type,
    jsonb_typeof(metadata) as metadata_type
FROM checkpoints
LIMIT 5;

-- Success message
DO $$
BEGIN
    RAISE NOTICE '✅ Column swap completed successfully!';
    RAISE NOTICE 'Old BYTEA columns dropped, JSONB columns renamed.';
    RAISE NOTICE 'Next step: Deploy updated LangGraph application.';
END $$;
