import argparse
import asyncio
import json
from datetime import datetime
from typing import Any
from src.config import env

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
        return value.replace('\x00', '')
    elif isinstance(value, dict):
        return {k: _sanitize_null_bytes(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_sanitize_null_bytes(item) for item in value]
    elif isinstance(value, tuple):
        return tuple(_sanitize_null_bytes(item) for item in value)
    else:
        return value


def _ensure_jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        sanitized = _sanitize_null_bytes(value)
        return sanitized
    except TypeError:
        # Fallback for LangChain message objects or other non-JSONables.
        dumped = dumpd(value)
        return _sanitize_null_bytes(dumped)


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
    cur.execute(
        """
        ALTER TABLE checkpoints
            ADD COLUMN IF NOT EXISTS checkpoint_jsonb JSONB,
            ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB;
        """
    )
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
        for row in rows:
            type_name = row["type"]
            blob = row["checkpoint"]
            if blob is None:
                continue

            checkpoint = serde.loads_typed((type_name, blob))
            checkpoint = _ensure_jsonable(checkpoint)

            updates.append(
                (
                    Jsonb(checkpoint),
                    row["thread_id"],
                    row["checkpoint_ns"],
                    row["checkpoint_id"],
                )
            )

        print(f"[{_ts()}] [chunk {chunk_index}] updates_prepared={len(updates)}")

        if updates and not dry_run:
            try:
                print(f"[{_ts()}] [chunk {chunk_index}] update_start")
                with cur.connection.transaction():
                    cur.executemany(
                        """
                        UPDATE checkpoints
                            SET checkpoint_jsonb = %s
                            WHERE thread_id = %s
                            AND checkpoint_ns = %s
                            AND checkpoint_id = %s;
                        """,
                        updates,
                    )
                    print(f"[{_ts()}] [chunk {chunk_index}] update_done")
            except Exception as exc:
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
                print(f"[{_ts()}] chunk {chunk_index} failed; details saved to {file_name}")
                raise

        migrated += len(updates)
        print(f"[{_ts()}] [progress] migrated_total={migrated}")

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
        dsn, autocommit=False, row_factory=dict_row
    ) as conn:
        async with conn.cursor() as cur:
            while True:
                # Fetch and lock a batch
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
                
                if not rows:
                    print(f"[{_ts()}] [worker {worker_id}] no more rows, exiting")
                    break
                
                chunk_index += 1
                print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] rows_fetched={len(rows)}")
                
                # Deserialize and prepare updates
                updates = []
                for row in rows:
                    type_name = row["type"]
                    blob = row["checkpoint"]
                    if blob is None:
                        continue
                    
                    checkpoint = serde.loads_typed((type_name, blob))
                    checkpoint = _ensure_jsonable(checkpoint)
                    
                    updates.append(
                        (
                            Jsonb(checkpoint),
                            row["thread_id"],
                            row["checkpoint_ns"],
                            row["checkpoint_id"],
                        )
                    )
                
                print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] updates_prepared={len(updates)}")
                
                if updates and not dry_run:
                    try:
                        print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] update_start")
                        async with conn.transaction():
                            await cur.executemany(
                                """
                                UPDATE checkpoints
                                    SET checkpoint_jsonb = %s
                                    WHERE thread_id = %s
                                    AND checkpoint_ns = %s
                                    AND checkpoint_id = %s;
                                """,
                                updates,
                            )
                        print(f"[{_ts()}] [worker {worker_id}] [chunk {chunk_index}] update_done")
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
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers (1 = sync mode)")
    parser.add_argument("--apply", action="store_true", help="Write changes.")
    args = parser.parse_args()

    dry_run = not args.apply
    serde = JsonPlusSerializer()
    dsn = _build_dsn(args)
    
    print(f"[{_ts()}] [step] connect: dsn={dsn}")
    
    # Setup columns and migrate metadata (sync, only once)
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            _ensure_columns(cur)
            
            if dry_run:
                print(f"[{_ts()}] dry-run mode: no updates will be written")
            else:
                print(f"[{_ts()}] [step] apply mode enabled")
            
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
        with psycopg.connect(dsn, autocommit=False, row_factory=dict_row) as conn:
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
