"""
Pre-deploy compatibility tests.

Verifies that the agent handles all three checkpoint scenarios without crashing:
  1. Legacy lc:1 message format (pre-migration history)
  2. New message format (threads processed after the migration fix)
  3. Fresh threads (new users, no history)

Prerequisites (local):
  - cloud-sql-proxy running
  - src/config/.env pointing to staging or prod
  - Vertex AI credentials exported (GOOGLE_APPLICATION_CREDENTIALS)

Run:
  uv run pytest tests/pre_deploy/ -v
"""

import uuid
import psycopg
import pytest
from psycopg.rows import dict_row
from langchain_core.messages import AIMessage

# All tests in this module share the session event loop so that the session-
# scoped `agent` fixture (which holds a psycopg pool and gRPC channel) is always
# accessed from the same loop it was created in.
pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# SQL (mirrored from queries.sql)
# ---------------------------------------------------------------------------

_Q_OLD_FORMAT = """
    SELECT DISTINCT thread_id
    FROM checkpoints
    WHERE checkpoint_ns = ''
      AND checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
    LIMIT 3
"""

_Q_NEW_FORMAT = """
    SELECT DISTINCT cb.thread_id
    FROM checkpoint_blobs cb
    WHERE cb.channel = 'messages'
      AND NOT EXISTS (
        SELECT 1 FROM checkpoints c
        WHERE c.thread_id = cb.thread_id
          AND c.checkpoint->'channel_values'->'messages' @> '[{"lc": 1}]'
      )
    LIMIT 3
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_thread_ids(dsn: str, query: str) -> list[str]:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '25s'")
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                return [row["thread_id"] for row in cur.fetchall()]
        except psycopg.errors.QueryCanceled:
            return []


async def _send_oi(agent, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return await agent.async_query(
        input={"messages": [{"role": "human", "content": "oi"}]},
        config=config,
    )


def _assert_valid_response(result: dict, thread_id: str):
    messages = result.get("messages", [])
    assert messages, f"[{thread_id}] Response has no messages"
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    assert ai_messages, f"[{thread_id}] Response has no AIMessage"
    assert ai_messages[-1].content, f"[{thread_id}] AIMessage has empty content"


def _extract_response(result: dict) -> str:
    """Return a short text excerpt from the last AIMessage content."""
    messages = result.get("messages", [])
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    if not ai_messages:
        return "(no AIMessage)"
    content = ai_messages[-1].content
    if isinstance(content, str):
        return content[:300]
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(parts)[:300]
    return str(content)[:300]


# ---------------------------------------------------------------------------
# Scenario 1 — legacy lc:1 format
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def legacy_thread_ids(dsn):
    ids = _fetch_thread_ids(dsn, _Q_OLD_FORMAT)
    if not ids:
        pytest.skip("No legacy-format threads found — scenario 1 skipped")
    return ids


@pytest.mark.parametrize("idx", [0, 1, 2])
async def test_legacy_format_thread(idx, legacy_thread_ids, agent, record_response):
    """Agent must load and respond to a thread with lc:1 legacy messages."""
    if idx >= len(legacy_thread_ids):
        pytest.skip(f"Only {len(legacy_thread_ids)} legacy threads found")
    thread_id = legacy_thread_ids[idx]
    print(f"\n  thread_id: {thread_id}")
    result = await _send_oi(agent, thread_id)
    _assert_valid_response(result, thread_id)
    record_response("legacy", thread_id, "oi", _extract_response(result))


# ---------------------------------------------------------------------------
# Scenario 2 — new message format
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def new_format_thread_ids(dsn):
    ids = _fetch_thread_ids(dsn, _Q_NEW_FORMAT)
    if not ids:
        pytest.skip("No new-format threads found — scenario 2 skipped")
    return ids


@pytest.mark.parametrize("idx", [0, 1, 2])
async def test_new_format_thread(idx, new_format_thread_ids, agent, record_response):
    """Agent must load and respond to a thread with new-format messages."""
    if idx >= len(new_format_thread_ids):
        pytest.skip(f"Only {len(new_format_thread_ids)} new-format threads found")
    thread_id = new_format_thread_ids[idx]
    print(f"\n  thread_id: {thread_id}")
    result = await _send_oi(agent, thread_id)
    _assert_valid_response(result, thread_id)
    record_response("new_format", thread_id, "oi", _extract_response(result))


# ---------------------------------------------------------------------------
# Scenario 3 — fresh threads (no history)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fresh_thread_ids():
    return [str(uuid.uuid4()) for _ in range(3)]


@pytest.mark.parametrize("idx", [0, 1, 2])
async def test_fresh_thread(idx, fresh_thread_ids, agent, record_response):
    """Agent must create and respond to a brand new thread."""
    thread_id = fresh_thread_ids[idx]
    print(f"\n  thread_id: {thread_id}")
    result = await _send_oi(agent, thread_id)
    _assert_valid_response(result, thread_id)
    record_response("fresh", thread_id, "oi", _extract_response(result))
    result = await _send_oi(agent, thread_id)
    _assert_valid_response(result, thread_id)


# ---------------------------------------------------------------------------
# Scenario 4 — deep checkpoint_ns must not overflow the PK index
# ---------------------------------------------------------------------------

def test_engine_has_no_src_imports():
    """
    engine/ must never import from src because src is not shipped during deploy.
    Any 'from src' or 'import src' inside engine/ will blow up on Vertex AI.
    """
    import re
    from pathlib import Path

    engine_root = Path(__file__).parent.parent.parent / "engine"
    pattern = re.compile(r"^\s*(from src[.\s]|import src[.\s])", re.MULTILINE)

    offenders = []
    for py_file in engine_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text()
        if pattern.search(text):
            offenders.append(str(py_file.relative_to(engine_root.parent)))

    assert not offenders, (
        "engine/ files must not import from src (src is not deployed):\n"
        + "\n".join(f"  {f}" for f in offenders)
    )


def test_safe_ns_short_is_unchanged():
    """Short namespaces must pass through unchanged."""
    from engine.agent import IntVersionPostgresSaver
    ns = "some_node:abc123|other_node:def456"
    assert IntVersionPostgresSaver._safe_ns(ns) == ns


def test_safe_ns_long_becomes_stable_hash():
    """Namespaces > 2500 bytes must be replaced with a stable 37-byte hash."""
    import hashlib
    from engine.agent import IntVersionPostgresSaver

    deep_ns = ("some_node:" + "x" * 30 + "|") * 70   # ~2800 bytes
    result = IntVersionPostgresSaver._safe_ns(deep_ns)

    assert result.startswith("hash:"), "hashed ns must start with 'hash:'"
    assert len(result) == 37, f"expected 37 bytes, got {len(result)}"
    # Idempotent / stable
    assert result == IntVersionPostgresSaver._safe_ns(deep_ns)
    # Correct hash value
    expected = "hash:" + hashlib.md5(deep_ns.encode()).hexdigest()
    assert result == expected


def test_get_next_version_does_not_grow():
    """get_next_version must not increase the digit count on repeated calls."""
    from engine.agent import IntVersionPostgresSaver

    saver = IntVersionPostgresSaver.__new__(IntVersionPostgresSaver)

    # Baseline: fresh thread — 17 digits (1-digit counter + 16 random)
    v = saver.get_next_version(None, "ch")
    assert len(str(v)) == 17, f"expected 17 digits from None, got {len(str(v))}"

    # Simulate a corrupted production version with 316 digits
    corrupted = int("3" * 300 + "1234567890123456")  # 316-digit current
    v2 = saver.get_next_version(corrupted, "ch")
    v3 = saver.get_next_version(v2, "ch")

    assert len(str(v2)) == len(str(v3)), (
        f"version grew from {len(str(v2))} to {len(str(v3))} digits — growth not stopped"
    )


def test_safe_version_with_huge_int():
    """_safe_version must hash values that exceed NS_VERSION_MAX_BYTES bytes."""
    import hashlib
    from engine.agent import IntVersionPostgresSaver

    huge = "9" * 2001  # 2001 bytes > default 2000-byte limit
    result = IntVersionPostgresSaver._safe_version(huge)

    assert result.startswith("hash:"), "hashed version must start with 'hash:'"
    assert len(result) == 37, f"expected 37-char hash, got {len(result)}"
    assert result == "hash:" + hashlib.md5(huge.encode()).hexdigest()

    # Short value must pass through unchanged
    assert IntVersionPostgresSaver._safe_version("12345") == "12345"


async def test_checkpoint_blob_deep_ns_does_not_overflow(dsn):
    """
    aput() with a checkpoint_ns > 2500 bytes must not raise
    psycopg.errors.ProgramLimitExceeded on the checkpoint_blobs_pkey or
    checkpoints_pkey indexes.
    """
    import hashlib
    from psycopg_pool import AsyncConnectionPool
    from engine.agent import IntVersionPostgresSaver

    # Realistic deeply-nested namespace produced by multi-step subgraph recursion
    deep_ns = ("some_node:" + "x" * 30 + "|") * 70   # ~2800 bytes
    thread_id = f"pytest-deep-ns-{uuid.uuid4()}"
    checkpoint_id = str(uuid.uuid4())

    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": deep_ns,
        }
    }
    checkpoint = {
        "v": 1,
        "id": checkpoint_id,
        "ts": "2024-01-01T00:00:00+00:00",
        "pending_sends": [],
        "versions_seen": {},
        "channel_versions": {},
        "channel_values": {},
    }

    async with AsyncConnectionPool(conninfo=dsn, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        saver = IntVersionPostgresSaver(conn=pool)

        try:
            # Must NOT raise ProgramLimitExceeded
            await saver.aput(config, checkpoint, {}, {})

            # aget_tuple must find the row using the same hashed ns
            result = await saver.aget_tuple(config)
            assert result is not None, "aget_tuple returned None for a just-written checkpoint"

        finally:
            # Always clean up test rows — both the real thread_id column value
            # and the hashed ns that the fix wrote to the DB.
            async with pool.connection() as conn:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    await conn.execute(
                        f"DELETE FROM {table} WHERE thread_id = %s",  # noqa: S608
                        (thread_id,),
                    )
