"""Unit tests for ``engine.caching.gemini_cache``.

Goal: cover the cache lifecycle without touching Vertex AI:
- First call creates a cache (cache_factory invoked exactly once).
- Same prompt + tools → hit (no re-create).
- Prompt change → previous cache deleted + new one created.
- Token count below ``min_tokens`` → explicit cache skipped (fallback to
  implicit).
- Factory exceptions degrade gracefully (no raise; reported via result).
- ``invalidate`` deletes the current cache and is idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

import pytest

from engine.caching.gemini_cache import (
    GEMINI_EXPLICIT_CACHE_MIN_TOKENS,
    GeminiCacheManager,
)


@dataclass
class FakeCache:
    """Stand-in for ``vertexai.caching.CachedContent``."""

    resource_name: str
    deleted: bool = False

    def delete(self) -> None:
        self.deleted = True


@dataclass
class FakeCacheFactory:
    """Records every ``create`` invocation and returns sequential fakes."""

    created: List[FakeCache] = field(default_factory=list)
    raise_on_call: bool = False

    def __call__(
        self,
        *,
        model_name: str,
        system_instruction,
        ttl: timedelta,
        display_name: Optional[str] = None,
    ) -> FakeCache:
        if self.raise_on_call:
            raise RuntimeError("vertexai unavailable")
        cache = FakeCache(resource_name=f"cachedContents/{len(self.created) + 1}")
        self.created.append(cache)
        return cache


SUFFICIENT_PROMPT = "PROMPT " * 2000  # ~14000 chars → ~3500 token heuristic — well above 1024


def _manager_with_factory(
    factory: Optional[FakeCacheFactory] = None,
    *,
    min_tokens: int = GEMINI_EXPLICIT_CACHE_MIN_TOKENS,
) -> tuple[GeminiCacheManager, FakeCacheFactory]:
    factory = factory or FakeCacheFactory()
    manager = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=factory,
        min_tokens=min_tokens,
    )
    return manager, factory


def test_first_call_creates_cache():
    manager, factory = _manager_with_factory()
    result = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    assert result.created is True
    assert result.hit is False
    assert result.skipped_below_min is False
    assert result.cached_content == "cachedContents/1"
    assert len(factory.created) == 1


def test_same_prompt_is_hit_without_recreate():
    manager, factory = _manager_with_factory()
    first = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    second = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    assert first.created is True
    assert second.created is False
    assert second.hit is True
    assert second.cached_content == first.cached_content
    assert len(factory.created) == 1


def test_prompt_change_creates_new_and_deletes_old():
    manager, factory = _manager_with_factory()
    first = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    second = manager.ensure_cache(SUFFICIENT_PROMPT + " extra", tools_signature="sig-v1")
    assert first.prompt_hash != second.prompt_hash
    assert second.created is True
    assert second.cached_content == "cachedContents/2"
    # Old cache must have been deleted.
    assert factory.created[0].deleted is True


def test_tools_signature_change_creates_new_cache():
    manager, factory = _manager_with_factory()
    manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    second = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v2")
    assert second.created is True
    assert len(factory.created) == 2
    assert factory.created[0].deleted is True


def test_below_min_tokens_skips_explicit_cache():
    manager, factory = _manager_with_factory(min_tokens=GEMINI_EXPLICIT_CACHE_MIN_TOKENS)
    short_prompt = "Short prompt"  # Heuristic: 12 / 4 = 3 tokens.
    result = manager.ensure_cache(short_prompt)
    assert result.skipped_below_min is True
    assert result.cached_content is None
    assert factory.created == []


def test_below_min_skips_then_above_min_creates():
    manager, factory = _manager_with_factory(min_tokens=10)
    # First prompt too small.
    short = "abcde" * 5  # ~25/4 = 6 tokens → below 10
    short_result = manager.ensure_cache(short)
    assert short_result.skipped_below_min is True
    # Second prompt above threshold → cache should mint.
    longer = "a" * 1000  # ~250 tokens
    longer_result = manager.ensure_cache(longer)
    assert longer_result.created is True
    assert longer_result.cached_content is not None


def test_factory_failure_returns_result_without_raising():
    manager, factory = _manager_with_factory(FakeCacheFactory(raise_on_call=True))
    result = manager.ensure_cache(SUFFICIENT_PROMPT)
    assert result.created is False
    assert result.hit is False
    assert result.skipped_below_min is False
    assert result.cached_content is None


def test_invalidate_deletes_current_cache_and_is_idempotent():
    manager, factory = _manager_with_factory()
    manager.ensure_cache(SUFFICIENT_PROMPT)
    assert manager.current_resource_name == "cachedContents/1"
    assert manager.invalidate() is True
    assert manager.current_resource_name is None
    assert factory.created[0].deleted is True
    # Second invalidate is a no-op.
    assert manager.invalidate() is False


def test_invalidate_after_no_cache_is_safe():
    manager, _ = _manager_with_factory()
    assert manager.invalidate() is False


def test_injected_token_counter_is_used():
    """If a real token counter is supplied, it overrides the heuristic."""
    counts: list[str] = []

    def fake_counter(text: str) -> int:
        counts.append(text)
        return 100  # Always below the 1024 default.

    manager = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=FakeCacheFactory(),
        token_counter=fake_counter,
    )
    result = manager.ensure_cache("any prompt at all")
    assert result.skipped_below_min is True
    # Counter was actually consulted.
    assert counts == ["any prompt at all"]


def test_token_counter_exception_falls_back_to_heuristic():
    """If the counter raises, the manager should not crash."""

    def bad_counter(text: str) -> int:
        raise RuntimeError("counter unavailable")

    manager = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=FakeCacheFactory(),
        token_counter=bad_counter,
        min_tokens=10,
    )
    # Long enough to pass the heuristic ~chars/4 → token count high.
    result = manager.ensure_cache("a" * 2000)
    assert result.created is True


def test_hash_changes_with_model_name_indirectly():
    """Two managers with different model names compute different hashes."""
    flash = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=FakeCacheFactory(),
    )
    pro = GeminiCacheManager(
        model_name="gemini-2.5-pro",
        cache_factory=FakeCacheFactory(),
    )
    flash_hash = flash._compute_hash(SUFFICIENT_PROMPT, "sig")
    pro_hash = pro._compute_hash(SUFFICIENT_PROMPT, "sig")
    assert flash_hash != pro_hash


def test_current_hash_exposed_after_create():
    manager, _ = _manager_with_factory()
    result = manager.ensure_cache(SUFFICIENT_PROMPT, "sig")
    assert manager.current_hash == result.prompt_hash


def test_expired_cache_is_recreated_on_next_ensure():
    """Once TTL elapses (with skew), the next ``ensure_cache`` mints a new
    resource and deletes the stale one — fixing the codex P2 finding.
    """
    from datetime import datetime, timedelta, timezone

    factory = FakeCacheFactory()
    clock_holder = {"now": datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)}

    def fake_clock() -> datetime:
        return clock_holder["now"]

    manager = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=factory,
        ttl=timedelta(hours=1),
        expiry_skew=timedelta(seconds=0),
        clock=fake_clock,
    )

    first = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    assert first.created is True
    # Hot path before expiry — must hit.
    clock_holder["now"] += timedelta(minutes=30)
    second = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    assert second.hit is True
    assert len(factory.created) == 1
    # Now advance past TTL.
    clock_holder["now"] += timedelta(hours=1)
    third = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig-v1")
    assert third.created is True
    assert third.hit is False
    assert factory.created[0].deleted is True
    assert len(factory.created) == 2


def test_expiry_skew_triggers_rebuild_before_actual_ttl():
    """When ``clock() + skew >= expires_at`` we should rebuild proactively
    so requests never see a Vertex cache moments away from eviction.
    """
    from datetime import datetime, timedelta, timezone

    factory = FakeCacheFactory()
    clock_holder = {"now": datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)}

    manager = GeminiCacheManager(
        model_name="gemini-2.5-flash",
        cache_factory=factory,
        ttl=timedelta(minutes=10),
        expiry_skew=timedelta(minutes=2),
        clock=lambda: clock_holder["now"],
    )

    manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig")
    # Advance to within the skew window (8 of 10 minutes elapsed).
    clock_holder["now"] += timedelta(minutes=8, seconds=1)
    result = manager.ensure_cache(SUFFICIENT_PROMPT, tools_signature="sig")
    assert result.created is True
    assert len(factory.created) == 2
