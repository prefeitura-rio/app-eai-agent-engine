# `checkpoint_blobs` Pruning Job

## Background

LangGraph's `AsyncPostgresSaver` stores checkpoint channel data in `checkpoint_blobs`:

```sql
CREATE TABLE checkpoint_blobs (
    thread_id      TEXT NOT NULL,
    checkpoint_ns  TEXT NOT NULL DEFAULT '',
    channel        TEXT NOT NULL,
    version        TEXT NOT NULL,
    type           TEXT NOT NULL,
    blob           BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
```

The upsert query uses `ON CONFLICT DO NOTHING`:

```sql
INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, version, type, blob)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (thread_id, checkpoint_ns, channel, version) DO NOTHING
```

Our `IntVersionPostgresSaver.get_next_version()` appends 16 random digits to every version
number, meaning **versions never collide by design**. Combined with `ON CONFLICT DO NOTHING`,
this means **old blob rows are never updated or deleted** — every write to a channel creates a
new row, indefinitely.

## Why This Grows Unboundedly

For a single channel in a single thread, every agent step produces a new `(version)` value.
A thread that runs 1 000 steps accumulates ≥ 1 000 rows **per channel** in `checkpoint_blobs`.
Typical threads have 10–30 channels, so even a moderately active thread can produce tens of
thousands of rows that are never read again after the thread advances past them.

Unlike `checkpoints` (where only the latest `N` checkpoints matter), old `checkpoint_blobs`
rows are purely historical artefacts once a newer version of the same channel exists.

## Safe Delete Rule

A `checkpoint_blobs` row for `(thread_id, checkpoint_ns, channel, version=V)` is **safe to
delete** when there exists a newer version `V' > V` for the same `(thread_id, checkpoint_ns,
channel)` **AND** the row is not referenced by any checkpoint that is still being kept.

Simplified safe condition (assuming we keep the latest checkpoint per thread):

```sql
-- Rows that are NOT the latest version for their (thread, ns, channel)
WITH latest AS (
    SELECT thread_id, checkpoint_ns, channel, MAX(version) AS latest_version
    FROM checkpoint_blobs
    GROUP BY thread_id, checkpoint_ns, channel
)
DELETE FROM checkpoint_blobs cb
USING latest l
WHERE cb.thread_id     = l.thread_id
  AND cb.checkpoint_ns = l.checkpoint_ns
  AND cb.channel       = l.channel
  AND cb.version      != l.latest_version;
```

> **Warning**: `version` is stored as TEXT. `MAX(version)` over TEXT uses lexicographic
> ordering, which is incorrect for our numeric versions (e.g. `"9..."` > `"10..."`).
> The query must cast to NUMERIC or use a different ordering strategy. See the note below.

### Correct Ordering for `IntVersion` Versions

Our versions are large integers stored as TEXT. Safe ordering:

```sql
WITH latest AS (
    SELECT thread_id, checkpoint_ns, channel,
           MAX(version::NUMERIC) AS latest_version_num
    FROM checkpoint_blobs
    GROUP BY thread_id, checkpoint_ns, channel
),
latest_text AS (
    SELECT cb.thread_id, cb.checkpoint_ns, cb.channel, cb.version
    FROM checkpoint_blobs cb
    JOIN latest l
      ON  cb.thread_id     = l.thread_id
      AND cb.checkpoint_ns = l.checkpoint_ns
      AND cb.channel       = l.channel
      AND cb.version::NUMERIC = l.latest_version_num
)
DELETE FROM checkpoint_blobs cb
WHERE NOT EXISTS (
    SELECT 1 FROM latest_text lt
    WHERE lt.thread_id     = cb.thread_id
      AND lt.checkpoint_ns = cb.checkpoint_ns
      AND lt.channel       = cb.channel
      AND lt.version       = cb.version
);
```

> **Note on hashed versions**: After `_safe_version()` is deployed, pathologically large
> versions are stored as `hash:<md5hex>`. These are 37-byte strings and will not cast to
> NUMERIC. The pruning query must handle both forms. The simplest approach: keep rows where
> `version` is the lexicographically maximum non-hash version, or keep all `hash:` rows
> (they represent the same logical "very large" counter anyway).

## Scope of Impact

| Table | Growth driver | Row accumulation rate |
|---|---|---|
| `checkpoint_blobs` | one new row per channel per step | high — target of this job |
| `checkpoints` | one row per step (replaces previous for `thread_id+ns+checkpoint_id`) | moderate |
| `checkpoint_writes` | intermediate write records | moderate |

## Implementation Approach

This job is intentionally **out of scope** for the current fix branch (`fix/growing_messages`).
It should be a separate, well-tested maintenance task before being run on production.

Recommended approach:
1. **Script**: standalone Python or SQL script in `scripts/` folder.
2. **Dry-run mode**: count rows that would be deleted before actually deleting.
3. **Batch deletes**: `DELETE ... LIMIT 10000` in a loop to avoid long lock holds.
4. **Thread-scoped**: optionally accept a `--thread-id` argument to prune a single thread.
5. **Cloud SQL `pg_cron`** (optional): schedule nightly via Cloud SQL's `pg_cron` extension
   once the script is validated.

## Related Files

- `engine/agent.py` — `IntVersionPostgresSaver`, `get_next_version`, `_safe_version`
- `engine/agent.py` — `_safe_ns` (companion overflow guard for `checkpoint_ns` column)
- LangGraph source: `.venv/lib/python3.13/site-packages/langgraph/checkpoint/postgres/base.py`
- LangGraph source: `.venv/lib/python3.13/site-packages/langgraph/checkpoint/postgres/aio.py`
