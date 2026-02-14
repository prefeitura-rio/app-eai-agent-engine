-- ============================================
-- CHECKPOINT MIGRATION VERIFICATION SCRIPT
-- ============================================

-- 1. Check total rows
SELECT 
    'Total Rows' as check_name,
    COUNT(*) as count
FROM checkpoints;

-- 2. Check migration completeness
SELECT 
    'Rows with checkpoint_jsonb' as check_name,
    COUNT(*) as count
FROM checkpoints 
WHERE checkpoint_jsonb IS NOT NULL;

SELECT 
    'Rows with metadata_jsonb' as check_name,
    COUNT(*) as count
FROM checkpoints 
WHERE metadata_jsonb IS NOT NULL;

-- 3. Check for unmigrated rows
SELECT 
    'Unmigrated checkpoints (CRITICAL)' as check_name,
    COUNT(*) as count
FROM checkpoints 
WHERE checkpoint IS NOT NULL AND checkpoint_jsonb IS NULL;

SELECT 
    'Unmigrated metadata' as check_name,
    COUNT(*) as count
FROM checkpoints 
WHERE metadata IS NOT NULL AND metadata_jsonb IS NULL;

-- 4. Sample data integrity check (first 5 rows)
SELECT 
    thread_id,
    checkpoint_ns,
    checkpoint_id,
    CASE 
        WHEN checkpoint IS NOT NULL THEN 'BYTEA present'
        ELSE 'BYTEA null'
    END as checkpoint_status,
    CASE 
        WHEN checkpoint_jsonb IS NOT NULL THEN 'JSONB present'
        ELSE 'JSONB null'
    END as checkpoint_jsonb_status,
    jsonb_typeof(checkpoint_jsonb) as jsonb_type,
    pg_column_size(checkpoint) as bytea_size_bytes,
    pg_column_size(checkpoint_jsonb) as jsonb_size_bytes
FROM checkpoints
WHERE checkpoint_jsonb IS NOT NULL
ORDER BY thread_id, checkpoint_ns, checkpoint_id
LIMIT 5;

-- 5. Check for JSONB structure integrity
SELECT 
    'Valid JSONB structure' as check_name,
    COUNT(*) as count
FROM checkpoints
WHERE checkpoint_jsonb IS NOT NULL 
  AND jsonb_typeof(checkpoint_jsonb) = 'object';

-- 6. Check column types
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'checkpoints'
  AND column_name IN ('checkpoint', 'checkpoint_jsonb', 'metadata', 'metadata_jsonb')
ORDER BY column_name;

-- 7. Check index status
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'checkpoints'
  AND indexname LIKE '%jsonb%';

-- 8. Estimate storage savings (JSONB is typically larger)
SELECT 
    'Original BYTEA total' as metric,
    pg_size_pretty(SUM(pg_column_size(checkpoint))) as size
FROM checkpoints
WHERE checkpoint IS NOT NULL
UNION ALL
SELECT 
    'New JSONB total' as metric,
    pg_size_pretty(SUM(pg_column_size(checkpoint_jsonb))) as size
FROM checkpoints
WHERE checkpoint_jsonb IS NOT NULL;
