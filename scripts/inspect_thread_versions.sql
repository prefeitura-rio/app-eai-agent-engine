-- ============================================================================
-- Script to inspect version types for a specific thread_id
-- Usage: Replace 'YOUR_THREAD_ID_HERE' with the actual thread_id
-- ============================================================================

-- Set the thread_id to inspect
\set thread_id 'YOUR_THREAD_ID_HERE'

\echo '==================================================================='
\echo 'INSPECTING VERSION TYPES FOR THREAD:'
\echo :thread_id
\echo '==================================================================='

-- 1. Count checkpoints for this thread
\echo ''
\echo '1. Checkpoint count for this thread:'
SELECT COUNT(*) as checkpoint_count
FROM checkpoints
WHERE thread_id = :'thread_id';

-- 2. Show recent checkpoints with their checkpoint_id
\echo ''
\echo '2. Recent checkpoints (last 5):'
SELECT 
    checkpoint_id,
    checkpoint_ns,
    CASE 
        WHEN checkpoint IS NOT NULL THEN 'JSONB'
        ELSE 'NULL'
    END as storage_type
FROM checkpoints
WHERE thread_id = :'thread_id'
ORDER BY checkpoint_id DESC
LIMIT 5;

-- 3. Inspect channel_versions data types in JSONB (most recent)
\echo ''
\echo '3. Channel versions from MOST RECENT checkpoint (JSONB types):'
WITH recent_checkpoint AS (
    SELECT checkpoint_jsonb
    FROM checkpoints
    WHERE thread_id = :'thread_id'
      AND checkpoint_jsonb IS NOT NULL
    ORDER BY checkpoint_id DESC
    LIMIT 1
)
SELECT 
    key as channel_name,
    value as version_value,
    jsonb_typeof(value) as jsonb_type,
    CASE 
        WHEN jsonb_typeof(value) = 'string' THEN '⚠️  STRING (PROBLEM!)'
        WHEN jsonb_typeof(value) = 'number' THEN '✅ NUMBER (CORRECT)'
        ELSE '❓ ' || jsonb_typeof(value)
    END as status
FROM recent_checkpoint,
     jsonb_each(checkpoint_jsonb->'channel_versions')
ORDER BY key
LIMIT 10;

-- 4. Check versions_seen structure
\echo ''
\echo '4. Versions seen structure (nested types):'
WITH recent_checkpoint AS (
    SELECT checkpoint_jsonb
    FROM checkpoints
    WHERE thread_id = :'thread_id'
      AND checkpoint_jsonb IS NOT NULL
    ORDER BY checkpoint_id DESC
    LIMIT 1
)
SELECT 
    jsonb_pretty(checkpoint_jsonb->'versions_seen') as versions_seen_sample
FROM recent_checkpoint;

-- 5. Raw JSONB sample
\echo ''
\echo '5. Raw channel_versions JSONB (first 500 chars):'
WITH recent_checkpoint AS (
    SELECT checkpoint_jsonb
    FROM checkpoints
    WHERE thread_id = :'thread_id'
      AND checkpoint_jsonb IS NOT NULL
    ORDER BY checkpoint_id DESC
    LIMIT 1
)
SELECT 
    LEFT((checkpoint_jsonb->'channel_versions')::text, 500) as channel_versions_raw
FROM recent_checkpoint;

-- 6. Check if there are any string versions in the entire thread's history
\echo ''
\echo '6. Summary: String versions detected in thread history?'
WITH thread_checkpoints AS (
    SELECT checkpoint_jsonb
    FROM checkpoints
    WHERE thread_id = :'thread_id'
      AND checkpoint_jsonb IS NOT NULL
)
SELECT 
    COUNT(*) as total_checkpoints,
    COUNT(CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM jsonb_each(checkpoint_jsonb->'channel_versions') 
            WHERE jsonb_typeof(value) = 'string'
        ) THEN 1 
    END) as checkpoints_with_string_versions,
    CASE 
        WHEN COUNT(CASE 
            WHEN EXISTS (
                SELECT 1 
                FROM jsonb_each(checkpoint_jsonb->'channel_versions') 
                WHERE jsonb_typeof(value) = 'string'
            ) THEN 1 
        END) > 0 
        THEN '⚠️  YES - STRING VERSIONS FOUND!'
        ELSE '✅ NO - All versions are numeric'
    END as status
FROM thread_checkpoints;

\echo ''
\echo '==================================================================='
\echo 'INSPECTION COMPLETE'
\echo '==================================================================='
