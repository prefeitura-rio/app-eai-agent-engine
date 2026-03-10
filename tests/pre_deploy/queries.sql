-- =============================================================================
-- PRE-DEPLOY COMPATIBILITY QUERIES
-- Reference SQL for the three test scenarios in test_checkpoint_compat.py.
-- Table: checkpoints (~1.5M rows, JSONB checkpoint column)
--
-- Performance notes:
--   - LIMIT 3 stops the scan as soon as 3 results are found
--   - checkpoint_ns = '' targets only root checkpoints (one per thread turn)
--   - @> (containment) and ? (key exists) use the GIN index on checkpoint
--   - Legacy threads are the majority today → scenario 1 scan terminates fast
-- =============================================================================


-- SCENARIO 1: Threads with legacy lc:1 message format (pre-migration history)
-- Detects the dict format produced by LangChain's dumpd():
--   {"lc": 1, "type": "constructor", "kwargs": {...}}
SELECT DISTINCT thread_id
FROM checkpoints
WHERE checkpoint_ns = ''
  AND checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
LIMIT 3;


-- SCENARIO 2: Threads with new message format (processed after migration fix)
-- Messages are stored in checkpoint_blobs as msgpack (not inline as lc:1 JSON).
-- Uses the checkpoint_blobs_pkey index + idx_checkpoints_thread_id for the
-- anti-join — executes in ~1ms despite 1.5M rows in checkpoints.
SELECT DISTINCT cb.thread_id
FROM checkpoint_blobs cb
WHERE cb.channel = 'messages'
  AND NOT EXISTS (
    SELECT 1 FROM checkpoints c
    WHERE c.thread_id = cb.thread_id
      AND c.checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
  )
LIMIT 3;


-- DIAGNOSTIC: count both categories (run manually before/after deploys)
-- legacy_format_count: threads with at least one lc:1 inline message
-- new_format_count: threads whose messages are only in checkpoint_blobs (msgpack)
SELECT
    COUNT(DISTINCT CASE WHEN checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
                        THEN thread_id END)  AS legacy_format_count,
    (
        SELECT COUNT(DISTINCT cb.thread_id)
        FROM checkpoint_blobs cb
        WHERE cb.channel = 'messages'
          AND NOT EXISTS (
            SELECT 1 FROM checkpoints c
            WHERE c.thread_id = cb.thread_id
              AND c.checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
          )
    )                                        AS new_format_count
FROM checkpoints
WHERE checkpoint_ns = '';
