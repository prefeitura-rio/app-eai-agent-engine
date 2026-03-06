import argparse
import json
import time
from datetime import datetime
from typing import Any

try:
    import orjson
    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False
    print("[WARNING] orjson not available, using slower json library. Install with: pip install orjson")

import pg8000.dbapi

from langchain_core.load.dump import dumpd
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from google.cloud.sql.connector import Connector


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
    # This function is no longer building a DSN string, but we can use it
    # to validate and return required connection parameters.
    instance_connection_name = ""
    db_user = ""
    db_pass = ""
    db_name = ""

    if not all([instance_connection_name, db_user, db_pass, db_name]):
        raise SystemExit("Missing required environment variables: INSTANCE_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME")

    # We'll return the instance connection name which is key for the connector.
    return instance_connection_name


def _ensure_columns(cur: pg8000.dbapi.Cursor) -> None:
    print(f"[{_ts()}] [step] ensure_columns: start")
    try:
        cur.execute(
            """
            ALTER TABLE checkpoints
                ADD COLUMN IF NOT EXISTS checkpoint_jsonb JSONB,
                ADD COLUMN IF NOT EXISTS metadata_jsonb JSONB;
            """
        )
        print(f"[{_ts()}] [step] ensure_columns: columns added")
        
        # Create index on checkpoint_jsonb to speed up WHERE checkpoint_jsonb IS NULL
        print(f"[{_ts()}] [step] ensure_columns: creating index...")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_checkpoints_jsonb_null 
            ON checkpoints (thread_id, checkpoint_ns, checkpoint_id) 
            WHERE checkpoint_jsonb IS NULL;
            """
        )
        print(f"[{_ts()}] [step] ensure_columns: index created")
        print(f"[{_ts()}] [step] ensure_columns: done")
    except Exception as exc:
        print(f"[{_ts()}] [step] ensure_columns: ERROR: {exc}")
        raise
    return


def _migrate_metadata(conn) -> int:
    print(f"[{_ts()}] [step] migrate_metadata: start")
    cur = conn.cursor()
    try:
        print(f"[{_ts()}] [migrate_metadata] executing UPDATE query...")
        cur.execute(
            """
            UPDATE checkpoints
                 SET metadata_jsonb = convert_from(metadata, 'UTF8')::jsonb
             WHERE metadata_jsonb IS NULL
                 AND metadata IS NOT NULL;
            """
        )
        print(f"[{_ts()}] [migrate_metadata] query executed, committing...")
        conn.commit()
        rowcount = cur.rowcount or 0
        print(f"[{_ts()}] [migrate_metadata] committed, rowcount={rowcount}")
    except Exception as exc:
        print(f"[{_ts()}] [migrate_metadata] ERROR: {exc}")
        print(f"[{_ts()}] [migrate_metadata] rolling back...")
        conn.rollback()
        raise
    finally:
        cur.close()
    print(f"[{_ts()}] [step] migrate_metadata: done")
    return rowcount


def _fetch_batch(cur, batch_size: int, last_key: tuple = None) -> list[dict]:
    print(f"[{_ts()}] [fetch_batch] start: batch_size={batch_size}, last_key={last_key}")
    try:
        if last_key is None:
            # First batch - no ORDER BY needed, index maintains order
            cur.execute(
                """
                SELECT thread_id,
                       checkpoint_ns,
                       checkpoint_id,
                       type,
                       checkpoint
                  FROM checkpoints
                 WHERE checkpoint_jsonb IS NULL
                 LIMIT %s;
                """,
                (batch_size,),
            )
        else:
            # Subsequent batches - keyset pagination
            thread_id, checkpoint_ns, checkpoint_id = last_key
            cur.execute(
                """
                SELECT thread_id,
                       checkpoint_ns,
                       checkpoint_id,
                       type,
                       checkpoint
                  FROM checkpoints
                 WHERE checkpoint_jsonb IS NULL
                   AND (thread_id, checkpoint_ns, checkpoint_id) > (%s, %s, %s)
                 ORDER BY thread_id, checkpoint_ns, checkpoint_id
                 LIMIT %s;
                """,
                (thread_id, checkpoint_ns, checkpoint_id, batch_size),
            )
        print(f"[{_ts()}] [fetch_batch] query executed, fetching rows...")
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cur.description]
        
        # Fetch all rows and convert to dicts
        raw_rows = cur.fetchall()
        rows = [dict(zip(columns, row)) for row in raw_rows]
        
        print(f"[{_ts()}] [fetch_batch] fetched {len(rows)} rows")
        return rows
    except Exception as exc:
        print(f"[{_ts()}] [fetch_batch] ERROR: {exc}")
        raise


def _migrate_checkpoints(
    conn,
    serde: JsonPlusSerializer,
    batch_size: int,
    dry_run: bool,
) -> int:
    migrated = 0
    chunk_index = 0
    last_key = None
    commits_pending = 0
    COMMIT_EVERY = 3  # Commit every N batches instead of every batch
    
    print(f"[{_ts()}] [step] migrate_checkpoints: start dry_run={dry_run} batch_size={batch_size}")

    try:
        cur = conn.cursor()
        print(f"[{_ts()}] [migrate_checkpoints] cursor created")
    except Exception as exc:
        print(f"[{_ts()}] [migrate_checkpoints] ERROR creating cursor: {exc}")
        raise

    while True:
        print(f"[{_ts()}] [migrate_checkpoints] loop iteration {chunk_index + 1}")
        
        try:
            rows = _fetch_batch(cur, batch_size, last_key)
        except Exception as exc:
            print(f"[{_ts()}] [migrate_checkpoints] ERROR fetching batch: {exc}")
            raise
        
        if not rows:
            # Commit any pending updates before finishing
            if commits_pending > 0 and not dry_run:
                print(f"[{_ts()}] [step] migrate_checkpoints: committing final batch...")
                conn.commit()
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
            try:
                type_name = row["type"]
                blob = row["checkpoint"]
                if blob is None:
                    print(f"[{_ts()}] [chunk {chunk_index}] row {i}: blob is None, skipping")
                    continue

                if i % 100 == 0 and i > 0:
                    print(f"[{_ts()}] [chunk {chunk_index}] deserializing row {i}/{len(rows)} (deser={t_deserialize:.1f}s, sanit={t_sanitize:.1f}s, json={t_json:.1f}s)")
                
                t1 = time.time()
                checkpoint = serde.loads_typed((type_name, blob))
                t_deserialize += time.time() - t1
                
                t2 = time.time()
                checkpoint = _ensure_jsonable(checkpoint)
                t_sanitize += time.time() - t2
                
                t3 = time.time()
                if USE_ORJSON:
                    checkpoint_json = orjson.dumps(checkpoint).decode('utf-8')
                else:
                    checkpoint_json = json.dumps(checkpoint)
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
            except Exception as exc:
                print(f"[{_ts()}] [chunk {chunk_index}] ERROR deserializing row {i}: {exc}")
                print(f"[{_ts()}] [chunk {chunk_index}] row data: thread_id={row['thread_id']}, type={row['type']}")
                raise

        # Update last_key for next iteration
        if rows:
            last_row = rows[-1]
            last_key = (last_row["thread_id"], last_row["checkpoint_ns"], last_row["checkpoint_id"])

        t_total = time.time() - t_start
        print(f"[{_ts()}] [chunk {chunk_index}] updates_prepared={len(updates)} in {t_total:.1f}s (deser={t_deserialize:.1f}s, sanit={t_sanitize:.1f}s, json={t_json:.1f}s)")

        if updates and not dry_run:
            try:
                print(f"[{_ts()}] [chunk {chunk_index}] update_start: executing {len(updates)} updates")
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
                commits_pending += 1
                print(f"[{_ts()}] [chunk {chunk_index}] executemany done")
                
                # Commit every COMMIT_EVERY batches
                if commits_pending >= COMMIT_EVERY:
                    print(f"[{_ts()}] [chunk {chunk_index}] committing {commits_pending} batches...")
                    conn.commit()
                    commits_pending = 0
                    print(f"[{_ts()}] [chunk {chunk_index}] commit done")
                else:
                    print(f"[{_ts()}] [chunk {chunk_index}] update done (commit pending: {commits_pending}/{COMMIT_EVERY})")
            except Exception as exc:
                print(f"[{_ts()}] [chunk {chunk_index}] ERROR during update: {exc}")
                print(f"[{_ts()}] [chunk {chunk_index}] rolling back...")
                conn.rollback()
                commits_pending = 0
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
        elif not updates:
            print(f"[{_ts()}] [chunk {chunk_index}] no updates to apply (all blobs were None)")
        elif dry_run:
            print(f"[{_ts()}] [chunk {chunk_index}] DRY RUN: would update {len(updates)} rows")

        migrated += len(updates)
        print(f"[{_ts()}] [progress] migrated_total={migrated}")

    print(f"[{_ts()}] [migrate_checkpoints] closing cursor...")
    cur.close()
    print(f"[{_ts()}] [step] migrate_checkpoints: done total={migrated}")
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate LangGraph checkpoints from BYTEA to JSONB."
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size (default: 1000)")
    parser.add_argument("--apply", action="store_true", help="Write changes.")
    args = parser.parse_args()

    dry_run = not args.apply
    
    try:
        print(f"[{_ts()}] [main] START - dry_run={dry_run}, batch_size={args.batch_size}")
        serde = JsonPlusSerializer()
        instance_connection_name = _build_dsn(args)
    
        print(f"[{_ts()}] [step] connect: instance={instance_connection_name}")
        
        # Initialize the synchronous connector
        print(f"[{_ts()}] [main] initializing Cloud SQL connector...")
        connector = Connector()
        db_user = ""
        db_pass = ""
        db_name = ""

        def getconn() -> pg8000.dbapi.Connection:
            print(f"[{_ts()}] [getconn] connecting to Cloud SQL...")
            conn = connector.connect(
                instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name,
                timeout=300  # 5 minute timeout
            )
            print(f"[{_ts()}] [getconn] connected successfully")
            return conn

        # Setup columns and migrate metadata
        print(f"[{_ts()}] [main] getting initial connection...")
        conn = getconn()
        conn.autocommit = False
        print(f"[{_ts()}] [main] creating cursor for column setup...")
        cur = conn.cursor()
        _ensure_columns(cur)
        print(f"[{_ts()}] [main] committing column changes...")
        conn.commit()
        cur.close()
        print(f"[{_ts()}] [main] column setup complete")
        
        if dry_run:
            print(f"[{_ts()}] dry-run mode: no updates will be written")
        else:
            print(f"[{_ts()}] [step] apply mode enabled")
        
        metadata_count = _migrate_metadata(conn) if not dry_run else 0
        print(f"[{_ts()}] [step] metadata rows updated: {metadata_count}")
        print(f"[{_ts()}] [main] closing metadata connection...")
        conn.close()
        
        # Migrate checkpoints
        print(f"[{_ts()}] [main] getting new connection for checkpoint migration...")
        conn = getconn()
        conn.autocommit = False
        print(f"[{_ts()}] [main] starting checkpoint migration...")
        migrated = _migrate_checkpoints(
            conn=conn,
            serde=serde,
            batch_size=args.batch_size,
            dry_run=dry_run,
        )
        print(f"[{_ts()}] [main] closing checkpoint connection...")
        conn.close()
        
        print(f"[{_ts()}] [step] checkpoints migrated: {migrated}")
        print(f"[{_ts()}] [main] closing connector...")
        connector.close()
        print(f"[{_ts()}] [main] COMPLETE")
    except Exception as exc:
        print(f"[{_ts()}] [main] FATAL ERROR: {exc}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
