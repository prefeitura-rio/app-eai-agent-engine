#!/usr/bin/env python3
"""
Quick validation test for checkpoint migration.
Tests that JSONB columns work correctly before column swap.
"""
import asyncio
import sys
from src.config import env

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("❌ psycopg not installed. Run: uv pip install psycopg[binary]")
    sys.exit(1)


async def test_migration():
    """Test that migration worked correctly."""
    dsn = f"postgresql://{env.DATABASE_USER}:{env.DATABASE_PASSWORD}@127.0.0.1:{env.DATABASE_PORT or '5432'}/{env.DATABASE}"
    
    print(f"🔍 Testing migration on: {env.DATABASE}")
    print("=" * 60)
    
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            # Test 1: Check total rows
            print("\n📊 Test 1: Row counts")
            await cur.execute("SELECT COUNT(*) as total FROM checkpoints;")
            result = await cur.fetchone()
            total_rows = result["total"]
            print(f"   Total rows: {total_rows:,}")
            
            # Test 2: Check migrated rows
            print("\n✅ Test 2: Migration completeness")
            await cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE checkpoint_jsonb IS NOT NULL) as migrated_checkpoints,
                    COUNT(*) FILTER (WHERE metadata_jsonb IS NOT NULL) as migrated_metadata,
                    COUNT(*) FILTER (WHERE checkpoint IS NOT NULL AND checkpoint_jsonb IS NULL) as unmigrated
                FROM checkpoints;
            """)
            result = await cur.fetchone()
            print(f"   Migrated checkpoints: {result['migrated_checkpoints']:,}")
            print(f"   Migrated metadata: {result['migrated_metadata']:,}")
            print(f"   Unmigrated (CRITICAL): {result['unmigrated']:,}")
            
            if result['unmigrated'] > 0:
                print(f"\n❌ FAIL: {result['unmigrated']:,} rows still unmigrated!")
                print("   Run: uv run scripts/migrate_checkpoints.py --apply --batch-size 50")
                return False
            
            # Test 3: JSONB operators work
            print("\n🔧 Test 3: JSONB operators")
            try:
                await cur.execute("""
                    SELECT checkpoint_jsonb->'channel_versions' as cv
                    FROM checkpoints
                    WHERE checkpoint_jsonb IS NOT NULL
                    LIMIT 1;
                """)
                result = await cur.fetchone()
                print(f"   ✅ JSONB -> operator works")
            except Exception as e:
                print(f"   ❌ JSONB operator test failed: {e}")
                return False
            
            # Test 4: Sample data
            print("\n📝 Test 4: Sample data structure")
            await cur.execute("""
                SELECT 
                    thread_id,
                    jsonb_typeof(checkpoint_jsonb) as checkpoint_type,
                    jsonb_typeof(metadata_jsonb) as metadata_type,
                    pg_column_size(checkpoint) as old_size,
                    pg_column_size(checkpoint_jsonb) as new_size
                FROM checkpoints
                WHERE checkpoint_jsonb IS NOT NULL
                LIMIT 3;
            """)
            rows = await cur.fetchall()
            for row in rows:
                print(f"   Thread: {row['thread_id'][:40]}...")
                print(f"   - Checkpoint type: {row['checkpoint_type']}")
                print(f"   - Metadata type: {row['metadata_type']}")
                print(f"   - Size change: {row['old_size']} → {row['new_size']} bytes")
            
            # Test 5: Check columns exist
            print("\n🏗️  Test 5: Schema check")
            await cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'checkpoints'
                  AND column_name IN ('checkpoint', 'checkpoint_jsonb', 'metadata', 'metadata_jsonb')
                ORDER BY column_name;
            """)
            columns = await cur.fetchall()
            print("   Current schema:")
            for col in columns:
                print(f"   - {col['column_name']}: {col['data_type']}")
            
            # Summary
            print("\n" + "=" * 60)
            print("✅ ALL TESTS PASSED!")
            print("\nNext steps:")
            print("1. Review MIGRATION_COMPLETION_PLAN.md")
            print("2. Create backup: pg_dump -h 127.0.0.1 -U eai-agent ...")
            print("3. Run: psql -f scripts/swap_columns.sql")
            return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_migration())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)