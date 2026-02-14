import argparse
import asyncio
import gc
import json
import time
import sys
from datetime import datetime
from typing import Any
from src.config import env

try:
    import orjson
    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False
    print("[WARNING] orjson not available, using slower json library. Install with: pip install orjson")

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from langchain_core.load.dump import dumpd
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _ts() -> str:
    """Return current timestamp in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


def _sanitize_null_bytes(value: Any) -> Any:
    """Recursively remove null bytes from strings (JSONB doesn't support \\u0000)."""
    if isinstance(value, str):
        # Only replace if null bytes exist (optimization)
        return value.replace('\x00', '') if '\x00' in value else value
    elif isinstance(value, dict):
        return {k: _sanitize_null_bytes(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_sanitize_null_bytes(item) for item in value]
    elif isinstance(value, tuple):
        return tuple(_sanitize_null_bytes(item) for item in value)
    else:
        return value


def _ensure_jsonable(value: Any) -> Any:
    """Convert checkpoint to JSON-serializable format, using dumpd() if needed."""
    # Try direct conversion first - most checkpoints are already json-serializable
    # Don't test with json.dumps() here - too expensive!
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    
    # For complex objects, try dumpd() first (LangChain serialization)
    # This handles message objects and other custom types
    try:
        # Most checkpoints need dumpd() conversion
        return dumpd(value)
    except Exception:
        # If dumpd() fails, return as-is and let json.dumps() handle it
        return value


def decode_checkpoint_bytea(type_name: str, blob: bytes) -> Any:
    """Decode a BYTEA checkpoint payload into JSON-serializable data."""
    serde = JsonPlusSerializer()
    checkpoint = serde.loads_typed((type_name, blob))
    return _ensure_jsonable(checkpoint)


def _build_dsn(args: argparse.Namespace) -> str:
    if args.dsn:
        return args.dsn

    host = "127.0.0.1"
    port = env.DATABASE_PORT or "5432"
    dbname = env.DATABASE
    user = env.DATABASE_USER
    password = env.DATABASE_PASSWORD

    missing = [k for k, v in {
        "DATABASE_HOST": host,
        "DATABASE": dbname,
        "DATABASE_USER": user,
        "DATABASE_PASSWORD": password,
    }.items() if not v]
    if missing:
        raise SystemExit(
            "Missing required env vars for DSN: " + ", ".join(missing)
        )

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _ensure_columns(cur: psycopg.Cursor) -> None:
    print(f"[{_ts()}] [step] ensure_columns: start")
    
    # Check if columns already exist
    cur.execute(
        """
        SELECT 
            EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'checkpoints' AND column_name = 'checkpoint_jsonb'
            ) AS checkpoint_exists,
            EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'checkpoints' AND column_name = 'metadata_jsonb'
            ) AS metadata_exists;
        """
    )
    result = cur.fetchone()
    checkpoint_exists = result["checkpoint_exists"]
    metadata_exists = result["metadata_exists"]
    
    if checkpoint_exists and metadata_exists:
        print(f"[{_ts()}] [step] ensure_columns: columns already exist, skipping ALTER TABLE")
    else:
        print(f"[{_ts()}] [step] ensure_columns: adding columns (this may take a while on large tables)...")
        cur.execute(
            """
            ALTER TABLE checkpoints
                ADD COLUMN IF NOT EXISTS checkpoint_jsonb JSONB,
                ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB;
            """
        )
        print(f"[{_ts()}] [step] ensure_columns: columns added")
    
    # Check if index already exists
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE tablename = 'checkpoints' 
            AND indexname = 'idx_checkpoints_jsonb_null'
        ) AS index_exists;
        """
    )
    index_exists = cur.fetchone()["index_exists"]
    
    if not index_exists:
        print(f"[{_ts()}] [step] ensure_columns: creating partial index (this may take several minutes)...")
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction, so ensure autocommit is on
        cur.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_checkpoints_jsonb_null 
            ON checkpoints (thread_id, checkpoint_ns, checkpoint_id) 
            WHERE checkpoint_jsonb IS NULL;
            """
        )
        print(f"[{_ts()}] [step] ensure_columns: index created")
    else:
        print(f"[{_ts()}] [step] ensure_columns: index already exists, skipping creation")
    
    print(f"[{_ts()}] [step] ensure_columns: done")
    return


def _migrate_metadata(cur: psycopg.Cursor) -> int:
    print(f"[{_ts()}] [step] migrate_metadata: start")
    with cur.connection.transaction():
        cur.execute(
            """
            UPDATE checkpoints
                 SET metadata_jsonb = convert_from(metadata, 'UTF8')::jsonb
             WHERE metadata_jsonb IS NULL
                 AND metadata IS NOT NULL;
            """
        )
    print(f"[{_ts()}] [step] migrate_metadata: done")
    return cur.rowcount or 0


def _fetch_batch(cur: psycopg.Cursor, batch_size: int) -> list[dict]:
    print(f"[{_ts()}] [step] fetch_batch: size={batch_size}")
    cur.execute(
        """
        SELECT thread_id,
               checkpoint_ns,
               checkpoint_id,
               type,
               checkpoint
          FROM checkpoints
         WHERE checkpoint_jsonb IS NULL
         LIMIT %s
           FOR UPDATE SKIP LOCKED;
        """,
        (batch_size,),
    )
    return list(cur.fetchall())


def _migrate_checkpoints(
    cur: psycopg.Cursor,
    serde: JsonPlusSerializer,
    batch_size: int,
    dry_run: bool,
) -> int:
    migrated = 0
    chunk_index = 0
    COMMIT_EVERY = 1  # Commit after EACH batch to reduce memory (was 3)
    
    print(f"[{_ts()}] [step] migrate_checkpoints: start dry_run={dry_run} batch_size={batch_size}")

    while True:
        # Fetch batch with lock (in transaction)
        with cur.connection.transaction():
            rows = _fetch_batch(cur, batch_size)
        
        if not rows:
            print(f"[{_ts()}] [step] migrate_checkpoints: no more rows")
            break
        chunk_index += 1
        print(f"[{_ts()}] [chunk {chunk_index}] rows_fetched={len(rows)}")

        updates = []
        t_start = time.time()
        print(f"[{_ts()}] [chunk {chunk_index}] starting deserialization...")
        
        t_deserialize = 0
        t_sanitize = 0
        t_json = 0
        
        for i, row in enumerate(rows):
            type_name = row["type"]
            blob = row["checkpoint"]
            if blob is None:
                continue

            # Heartbeat every 10 rows to prevent idle timeout
            if i % 10 == 0:
                sys.stdout.write('.')
                sys.stdout.flush()
            
            if i % 50 == 0 and i > 0:
                print(f"\n[{_ts()}] [chunk {chunk_index}] deserializing row {i}/{len(rows)} (deser={t_deserialize:.1f}s, sanit={t_sanitize:.1f}s, json={t_json:.1f}s)")
            
            t1 = time.time()
            checkpoint = serde.loads_typed((type_name, blob))
            t_deserialize += time.time() - t1
            
            t2 = time.time()
            # Try to serialize directly - most checkpoints are already JSON-serializable
            # Only call dumpd() if we get a TypeError
            if USE_ORJSON:
                try:
                    checkpoint_json = orjson.dumps(checkpoint).decode('utf-8')
                except TypeError:
                    # Fallback: use dumpd() for LangChain objects
                    checkpoint_json = orjson.dumps(dumpd(checkpoint)).decode('utf-8')
            else:
                try:
                    checkpoint_json = json.dumps(checkpoint)
                except TypeError:
                    # Fallback: use dumpd() for LangChain objects
                    checkpoint_json = json.dumps(dumpd(checkpoint))
            t_sanitize += time.time() - t2
            
            t3 = time.time()
            # Apply sanitization to the final JSON string (much faster than recursive)
            if '\x00' in checkpoint_json:
                checkpoint_json = checkpoint_json.replace('\x00', '')
            t_json += time.time() - t3

            updates.append(
                (
                    checkpoint_json,
                    row["thread_id"],
                    row["checkpoint_ns"],
                    row["checkpoint_id"],
                )
            )
            
            # Free memory: delete large objects immediately after use
            del checkpoint
            if i % 50 == 0:
                gc.collect()  # Force garbage collection periodically

        t_total = time.time() - t_start
        print(f"[{_ts()}] [chunk {chunk_index}] updates_prepared={len(updates)} in {t_total:.1f}s (deser={t_deserialize:.1f}s, sanit={t_sanitize:.1f}s, json={t_json:.1f}s)")

        if updates and not dry_run:
            try:
                t_update = time.time()
                print(f"[{_ts()}] [chunk {chunk_index}] update_start: executing {len(updates)} updates")
                with cur.connection.transaction():
                    cur.executemany(
                        """
                        UPDATE checkpoints
                            SET checkpoint_jsonb = %s::jsonb
                            WHERE thread_id = %s
                            AND checkpoint_ns = %s
                            AND checkpoint_id = %s;
                        """,
                        updates,
                    )
                print(f"[{_ts()}] [chunk {chunk_index}] executemany done in {time.time() - t_update:.1f}s, committing...")
                cur.connection.commit()  # Commit after EACH batch
                print(f"[{_ts()}] [chunk {chunk_index}] commit done")
            except Exception as exc:
                print(f"[{_ts()}] [chunk {chunk_index}] ERROR during update: {exc}")
                print(f"[{_ts()}] [chunk {chunk_index}] rolling back...")
                cur.connection.rollback()
                failed_chunk = {
                    "chunk_index": chunk_index,
                    "batch_size": batch_size,
                    "migrated_before_chunk": migrated,
                    "error": str(exc),
                    "rows": [
                        {
                            "thread_id": row["thread_id"],
                            "checkpoint_ns": row["checkpoint_ns"],
                            "checkpoint_id": row["checkpoint_id"],
                            "type": row["type"],
                        }
                        for row in rows
                    ],
                }
                file_name = f"migrate_failed_chunk_{chunk_index}.json"
                with open(file_name, "w", encoding="utf-8") as handle:
                    json.dump(failed_chunk, handle, indent=2)
                print(f"[{_ts()}] [chunk {chunk_index}] failed; details saved to {file_name}")
                raise

        migrated += len(updates)
        print(f"[{_ts()}] [progress] migrated_total={migrated}")
        
        # Free memory: clear updates list and force garbage collection
        del updates
        del rows
        gc.collect()

    print(f"[{_ts()}] [step] migrate_checkpoints: done total={migrated}")
    return migrated


async def _migrate_worker(
    worker_id: int,
    dsn: str,
    serde: JsonPlusSerializer,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Single async worker that processes batches until none remain."""
    migrated = 0
    chunk_index = 0
    
    async with await psycopg.AsyncConnection.connect(
        dsn, autocommit=False, row_factory=dict_row, options="-c statement_timeout=600000"  # 10 minute timeout for async workers
    ) as conn:
        async with conn.cursor() as cur:
            while True:
                # Fetch and lock a batch
                try:
                    async with conn.transaction():
                        await cur.execute(
                            """
                            SELECT thread_id,
                                   checkpoint_ns,
                                   checkpoint_id,
                                   type,
                                   checkpoint
                              FROM checkpoints
                             WHERE checkpoint_jsonb IS NULL
                             LIMIT %s
                               FOR UPDATE SKIP LOCKED;
                            """,
                            (batch_size,),
                        )
                        rows = await cur.fetchall()
                except Exception as exc:
                    print(f"[{_ts()}] [worker {worker_id}] ERROR fetching batch: {exc}")
                    # Continue to next iteration or exit if it's a fatal error
                    if "statement timeout" in str(exc).lower():
                        print(f"[{_ts()}] [worker {worker_id}] timeout on fetch, retrying...")
                        await asyncio.sleep(1)
                        continue
                    raise
                
                if not rows:
                    print(f"[{_ts()}] [worker {worker_id}] no more rows, exiting")
                    break
                
                chunk_index += 1
                print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] rows_fetched={len(rows)}")
                
                # Deserialize and prepare updates
                updates = []
                for i, row in enumerate(rows):
                    type_name = row["type"]
                    blob = row["checkpoint"]
                    if blob is None:
                        continue
                    
                    if i % 100 == 0 and i > 0:
                        print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] deserializing row {i}/{len(rows)}")
                    
                    checkpoint = serde.loads_typed((type_name, blob))
                    
                    # Try to serialize directly - most checkpoints are already JSON-serializable
                    if USE_ORJSON:
                        try:
                            checkpoint_json = orjson.dumps(checkpoint).decode('utf-8')
                        except TypeError:
                            checkpoint_json = orjson.dumps(dumpd(checkpoint)).decode('utf-8')
                    else:
                        try:
                            checkpoint_json = json.dumps(checkpoint)
                        except TypeError:
                            checkpoint_json = json.dumps(dumpd(checkpoint))
                    
                    # Apply sanitization to the final JSON string
                    if '\x00' in checkpoint_json:
                        checkpoint_json = checkpoint_json.replace('\x00', '')
                    
                    updates.append(
                        (
                            checkpoint_json,
                            row["thread_id"],
                            row["checkpoint_ns"],
                            row["checkpoint_id"],
                        )
                    )
                
                print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] updates_prepared={len(updates)}")
                
                if updates and not dry_run:
                    try:
                        t_update = time.time()
                        print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] update_start")
                        async with conn.transaction():
                            await cur.executemany(
                                """
                                UPDATE checkpoints
                                    SET checkpoint_jsonb = %s::jsonb
                                    WHERE thread_id = %s
                                    AND checkpoint_ns = %s
                                    AND checkpoint_id = %s;
                                """,
                                updates,
                            )
                        print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] update_done in {time.time() - t_update:.1f}s")
                    except Exception as exc:
                        failed_chunk = {
                            "worker_id": worker_id,
                            "chunk_index": chunk_index,
                            "batch_size": batch_size,
                            "migrated_before_chunk": migrated,
                            "error": str(exc),
                            "rows": [
                                {
                                    "thread_id": row["thread_id"],
                                    "checkpoint_ns": row["checkpoint_ns"],
                                    "checkpoint_id": row["checkpoint_id"],
                                    "type": row["type"],
                                }
                                for row in rows
                            ],
                        }
                        file_name = f"migrate_failed_worker{worker_id}_chunk{chunk_index}.json"
                        with open(file_name, "w", encoding="utf-8") as handle:
                            json.dump(failed_chunk, handle, indent=2)
                        print(f"[{_ts()}] [worker {worker_id}] chunk {chunk_index} failed; details saved to {file_name}")
                        raise
                
                migrated += len(updates)
                print(f"[{_ts()}] [worker {worker_id}] [progress] migrated_total={migrated}")
    
    print(f"[{_ts()}] [worker {worker_id}] done total={migrated}")
    return migrated


async def _migrate_checkpoints_async(
    dsn: str,
    serde: JsonPlusSerializer,
    batch_size: int,
    workers: int,
    dry_run: bool,
) -> int:
    """Spawn multiple workers to process checkpoints concurrently."""
    print(f"[{_ts()}] [step] migrate_checkpoints_async: starting {workers} workers, batch_size={batch_size}")
    
    tasks = [
        _migrate_worker(worker_id, dsn, serde, batch_size, dry_run)
        for worker_id in range(1, workers + 1)
    ]
    
    results = await asyncio.gather(*tasks)
    total = sum(results)
    
    print(f"[{_ts()}] [step] migrate_checkpoints_async: done total={total}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate LangGraph checkpoints from BYTEA to JSONB."
    )
    parser.add_argument("--dsn", help="Postgres DSN. If omitted, uses env vars.")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size (default: 500, increased for memory efficiency)")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers (default: 1). Multi-worker mode is experimental and may have lock contention issues.")
    parser.add_argument("--apply", action="store_true", help="Write changes.")
    args = parser.parse_args()

    dry_run = not args.apply
    serde = JsonPlusSerializer()
    dsn = _build_dsn(args)
    
    if args.workers > 1:
        print(f"[{_ts()}] [WARNING] Multi-worker mode ({args.workers} workers) may have lock contention issues. Consider using single-worker mode.")
    
    print(f"[{_ts()}] [step] connect: dsn={dsn}")
    
    # Setup columns (no timeout for DDL operations)
    print(f"[{_ts()}] [step] Setting up schema (no timeout for DDL operations)...")
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            _ensure_columns(cur)
    
    # Migrate metadata with timeout
    if dry_run:
        print(f"[{_ts()}] dry-run mode: no updates will be written")
    else:
        print(f"[{_ts()}] [step] apply mode enabled")
        
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row, options="-c statement_timeout=300000") as conn:
        with conn.cursor() as cur:
            metadata_count = _migrate_metadata(cur) if not dry_run else 0
            print(f"[{_ts()}] [step] metadata rows updated: {metadata_count}")
    
    # Migrate checkpoints (async if workers > 1, sync otherwise)
    if args.workers > 1:
        migrated = asyncio.run(
            _migrate_checkpoints_async(
                dsn=dsn,
                serde=serde,
                batch_size=args.batch_size,
                workers=args.workers,
                dry_run=dry_run,
            )
        )
    else:
        with psycopg.connect(dsn, autocommit=False, row_factory=dict_row, options="-c statement_timeout=300000") as conn:
            with conn.cursor() as cur:
                migrated = _migrate_checkpoints(
                    cur=cur,
                    serde=serde,
                    batch_size=args.batch_size,
                    dry_run=dry_run,
                )
    
    print(f"[{_ts()}] [step] checkpoints migrated: {migrated}")


if __name__ == "__main__":
    main()
