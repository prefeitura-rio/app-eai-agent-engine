#!/usr/bin/env python3
"""
Inspect version types for a specific thread_id in the database.
Usage: uv run python scripts/inspect_thread_versions.py THREAD_ID
"""
import sys
import asyncio
import psycopg
from psycopg.rows import dict_row

# Get thread_id from command line
if len(sys.argv) < 2:
    print("Usage: uv run python scripts/inspect_thread_versions.py THREAD_ID")
    print("Example: uv run python scripts/inspect_thread_versions.py test-new-thread-2026-03-09")
    sys.exit(1)

thread_id = sys.argv[1]


async def inspect_thread(thread_id: str):
    """Inspect version types for the given thread_id."""
    
    # Import config
    try:
        from src.config import env
        dsn = f"postgresql://{env.DATABASE_USER}:{env.DATABASE_PASSWORD}@127.0.0.1:{env.DATABASE_PORT or '5432'}/{env.DATABASE}"
    except ImportError:
        print("❌ Could not load config. Make sure cloud-sql-proxy is running.")
        return False
    
    print("=" * 80)
    print(f"🔍 INSPECTING VERSION TYPES FOR THREAD: {thread_id}")
    print("=" * 80)
    
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            
            # 1. Count checkpoints
            print("\n1️⃣  Checkpoint count:")
            await cur.execute(
                "SELECT COUNT(*) as count FROM checkpoints WHERE thread_id = %s",
                (thread_id,)
            )
            result = await cur.fetchone()
            print(f"   Total checkpoints: {result['count']}")
            
            if result['count'] == 0:
                print(f"\n⚠️  No checkpoints found for thread_id: {thread_id}")
                print("   This is a NEW thread - LangGraph will create fresh versions")
                return True
            
            # 2. Recent checkpoints
            print("\n2️⃣  Recent checkpoints (last 5):")
            await cur.execute(
                """
                SELECT checkpoint_id, checkpoint_ns,
                       CASE 
                           WHEN checkpoint IS NOT NULL THEN 'JSONB'
                           ELSE 'NULL'
                       END as storage_type
                FROM checkpoints
                WHERE thread_id = %s
                ORDER BY checkpoint_id DESC
                LIMIT 5
                """,
                (thread_id,)
            )
            rows = await cur.fetchall()
            for row in rows:
                ns_display = row['checkpoint_ns'] if row['checkpoint_ns'] else '(root)'
                print(f"   ID: {row['checkpoint_id'][:40]}... | NS: {ns_display} | Type: {row['storage_type']}")
            
            # 3. Inspect most recent checkpoint's channel_versions types
            print("\n3️⃣  Channel versions from MOST RECENT checkpoint:")
            await cur.execute(
                """
                WITH recent_checkpoint AS (
                    SELECT checkpoint
                    FROM checkpoints
                    WHERE thread_id = %s AND checkpoint IS NOT NULL
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                )
                SELECT key as channel_name,
                       value as version_value,
                       jsonb_typeof(value) as jsonb_type
                FROM recent_checkpoint,
                     jsonb_each(checkpoint->'channel_versions')
                ORDER BY key
                """,
                (thread_id,)
            )
            rows = await cur.fetchall()
            
            has_strings = False
            for row in rows:
                type_name = row['jsonb_type']
                status = "✅" if type_name == "number" else "⚠️ "
                if type_name == "string":
                    has_strings = True
                    status = "❌"
                
                print(f"   {status} {row['channel_name'][:30]:<30} = {str(row['version_value'])[:40]:<40} (type: {type_name})")
            
            # 4. Summary
            print("\n4️⃣  Summary - String versions detected?")
            await cur.execute(
                """
                WITH thread_checkpoints AS (
                    SELECT checkpoint
                    FROM checkpoints
                    WHERE thread_id = %s AND checkpoint IS NOT NULL
                )
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE 
                        WHEN EXISTS (
                            SELECT 1 
                            FROM jsonb_each(checkpoint->'channel_versions') 
                            WHERE jsonb_typeof(value) = 'string'
                        ) THEN 1 
                    END) as with_strings
                FROM thread_checkpoints
                """,
                (thread_id,)
            )
            result = await cur.fetchone()
            
            print(f"   Total checkpoints: {result['total']}")
            print(f"   Checkpoints with STRING versions: {result['with_strings']}")
            
            if result['with_strings'] > 0:
                print(f"\n   ❌ PROBLEM DETECTED: {result['with_strings']} checkpoint(s) have STRING versions!")
                print(f"   → This causes TypeError when comparing with integer versions")
                print(f"   → Solution: Run database migration to convert strings to integers")
                return False
            else:
                print(f"\n   ✅ GOOD: All versions are numeric (integers)")
                print(f"   → No database migration needed for this thread")
                return True
    
    print("\n" + "=" * 80)
    print("INSPECTION COMPLETE")
    print("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(inspect_thread(thread_id))
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
