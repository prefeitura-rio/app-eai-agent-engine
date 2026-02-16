-- ============================================
-- ROLLBACK SCRIPT (Emergency Use Only)
-- ============================================
-- Use this if the column swap causes issues
-- WARNING: This only works if you haven't dropped the old columns yet!
-- ============================================

-- Check if old columns still exist
SELECT 
    column_name
FROM information_schema.columns
WHERE table_name = 'checkpoints'
  AND column_name IN ('checkpoint', 'checkpoint_jsonb', 'metadata', 'metadata_jsonb');

-- If you see both checkpoint and checkpoint_jsonb, rollback is possible:

-- Option 1: Remove JSONB columns (keep BYTEA)
-- USE THIS IF: Migration failed and you want to revert
/*
ALTER TABLE checkpoints
    DROP COLUMN IF EXISTS checkpoint_jsonb,
    DROP COLUMN IF EXISTS metadata_jsonb;

DROP INDEX IF EXISTS idx_checkpoints_jsonb_null;
*/

-- Option 2: Restore from backup
-- USE THIS IF: You already swapped columns and need to restore
/*
-- 1. Export backup (run BEFORE column swap):
pg_dump -h 127.0.0.1 -U eai-agent -d eai-agent -t checkpoints \
    --column-inserts --data-only > checkpoints_backup.sql

-- 2. Restore from backup:
psql -h 127.0.0.1 -U eai-agent -d eai-agent < checkpoints_backup.sql
*/

-- Check column status after rollback
SELECT 
    'After Rollback' as status,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'checkpoints'
  AND column_name LIKE '%checkpoint%' OR column_name LIKE '%metadata%'
ORDER BY column_name;
