"""Vertex AI explicit-caching manager for Gemini system prompt + tools.

Why
~~~
Gemini 2.5 Flash already supports *implicit* caching (auto-on since 2026),
but the **explicit** path gives a deterministic 90% read discount on the
cached portion and lets us observe cache-hit metrics. The system prompt
in this Engine is ~12k tokens, so a single 1-hour cache costs ~$0.012 of
storage but each subsequent request saves >$0.0003 in input cost — break-
even is ~1 hit/hour. ([plano-bot-2026 §2.2](docs/propostas/plano-bot-2026.md).)

Constraints
~~~~~~~~~~~
- Gemini 2.5+ explicit cache **requires ≥ 1024 tokens** for Flash and
  ≥ 2048 for Pro. The Engine prompt is ~12k so we are above threshold,
  but the manager refuses to call ``CachedContent.create`` if the prompt
  hash maps to a content size below ``GEMINI_EXPLICIT_CACHE_MIN_TOKENS``
  (configurable for tests / future Pro use).
- TTL is configurable; default 1h. The cache survives across requests
  until ``invalidate`` is called or the system prompt hash changes.
- Hash uses SHA-256 over ``(model, system_prompt, tools_signature)``.
  Any drift in any input forces a rebuild on the next call.

Public surface
~~~~~~~~~~~~~~
- ``GeminiCacheManager`` — stateful singleton-per-Agent; thread-safe via
  a lock.
- ``ensure_cache(system_prompt, tools_signature) -> GeminiCacheResult``
  — returns ``cached_content`` resource name (for ``ChatVertexAI``) plus
  ``hit`` / ``created`` / ``skipped_below_min`` flags.
- ``invalidate()`` — best-effort delete; idempotent.

Observability
~~~~~~~~~~~~~
The manager records OTel histogram counts on ``gen_ai.cache.hit_count``
and ``gen_ai.cache.miss_count``. ``skipped_below_min`` outcomes are
recorded as a miss with an extra ``reason=below_min_tokens`` attribute so
the dashboard can surface the fallback path separately.

Testing
~~~~~~~
The manager accepts a ``cache_factory`` and ``token_counter`` (both
optional) for dependency injection — tests substitute fakes instead of
hitting Vertex AI.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Protocol

from opentelemetry import metrics

from engine.log import logger

# Default min-tokens for Gemini 2.5 Flash explicit cache.
# Pro is 2048; bump per project if/when Pro is wired up.
GEMINI_EXPLICIT_CACHE_MIN_TOKENS: int = 1024

# Default TTL: 1 hour (Google charges ~$1/M tokens/hour for Flash storage;
# 12k * $1/M = ~$0.012/hour so leaving the cache hot is cheap).
DEFAULT_TTL: timedelta = timedelta(hours=1)


@dataclass(frozen=True)
class GeminiCacheResult:
    """Outcome of a single :meth:`GeminiCacheManager.ensure_cache` call.

    Attributes
    ----------
    cached_content:
        Resource name (``cachedContents/<id>``) to pass to
        ``ChatVertexAI(cached_content=...)``. ``None`` if the cache could
        not be used (e.g. prompt below min-tokens fallback).
    hit:
        ``True`` if a previously-created cache was reused without
        creating a new one (hash unchanged + cache still valid).
    created:
        ``True`` if a new ``CachedContent`` was minted during this call.
    skipped_below_min:
        ``True`` if explicit caching was skipped because the system
        prompt is below the min-tokens threshold (implicit caching still
        applies in that case).
    prompt_hash:
        SHA-256 hex digest of the combined inputs, useful for debugging
        cache churn.
    """

    cached_content: Optional[str]
    hit: bool
    created: bool
    skipped_below_min: bool
    prompt_hash: str


class _CachedContentLike(Protocol):
    """Subset of ``vertexai.caching.CachedContent`` that the manager uses."""

    resource_name: str

    def delete(self) -> None: ...


class _CachedContentFactory(Protocol):
    """Callable that builds a CachedContent. Mirrors ``CachedContent.create``."""

    def __call__(
        self,
        *,
        model_name: str,
        system_instruction: Optional[Any],
        ttl: timedelta,
        display_name: Optional[str] = None,
    ) -> _CachedContentLike: ...


class _TokenCounter(Protocol):
    """Callable returning token count for a given text string."""

    def __call__(self, text: str) -> int: ...


@dataclass
class GeminiCacheManager:
    """Thread-safe explicit cache manager.

    A single ``GeminiCacheManager`` per ``Agent`` is the expected lifetime
    — callers re-use it across requests so the cache hash check stays
    fast.

    Parameters
    ----------
    model_name:
        Gemini model (e.g. ``gemini-2.5-flash``). Bound at construction
        because Vertex AI cache resources are model-scoped.
    ttl:
        How long the explicit cache should live before Vertex evicts it.
    min_tokens:
        Threshold under which explicit caching is skipped.
    cache_factory:
        Hook to build the cache (defaults to a Vertex SDK call). Tests
        inject a fake.
    token_counter:
        Optional callable returning token count for the system prompt.
        Defaults to a cheap heuristic (``len(text) // 4``); production
        callers can pass ``ChatVertexAI(...).get_num_tokens`` for a
        precise count.
    """

    model_name: str
    ttl: timedelta = DEFAULT_TTL
    min_tokens: int = GEMINI_EXPLICIT_CACHE_MIN_TOKENS
    cache_factory: Optional[_CachedContentFactory] = None
    token_counter: Optional[_TokenCounter] = None
    display_name: str = "engine-gemini-system-cache"

    # Skew applied when comparing ``now()`` against the recorded expiry.
    # Treat the cache as "about to expire" a little before the TTL elapses
    # so we never hand out a name Vertex is about to evict.
    expiry_skew: timedelta = timedelta(seconds=60)
    # Hook so tests can substitute a deterministic clock.
    clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc),
    )

    # Internal state. Not part of the public dataclass surface.
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _current_hash: Optional[str] = field(default=None, init=False, repr=False)
    _current_cache: Optional[_CachedContentLike] = field(default=None, init=False, repr=False)
    _current_expires_at: Optional[datetime] = field(default=None, init=False, repr=False)
    _last_skipped: bool = field(default=False, init=False, repr=False)

    def ensure_cache(
        self,
        system_prompt: str,
        tools_signature: str = "",
        *,
        extra_attributes: Optional[Mapping[str, str]] = None,
    ) -> GeminiCacheResult:
        """Return the current cache resource for ``system_prompt`` + ``tools``.

        On hash drift, the prior cache is deleted (best-effort) and a new
        one minted. On below-min-tokens prompt, falls back to no
        ``cached_content`` (caller still benefits from implicit caching).
        """
        prompt_hash = self._compute_hash(system_prompt, tools_signature)

        # Hot path: same prompt hash, cache still set, and TTL not expired → reuse.
        with self._lock:
            if (
                self._current_cache is not None
                and self._current_hash == prompt_hash
                and not self._is_expired_locked()
            ):
                self._record_metric(hit=True, extra_attributes=extra_attributes)
                return GeminiCacheResult(
                    cached_content=self._current_cache.resource_name,
                    hit=True,
                    created=False,
                    skipped_below_min=False,
                    prompt_hash=prompt_hash,
                )
            # If hash matches but cache expired, drop it now so the cold
            # path mints a fresh one (logged for observability).
            if (
                self._current_cache is not None
                and self._current_hash == prompt_hash
                and self._is_expired_locked()
            ):
                logger.info(
                    f"[GeminiCache] Cache {self._current_cache.resource_name} expired (or near-expiry); "
                    f"will recreate"
                )
                self._delete_current_locked()
                self._current_expires_at = None

        # Decide before holding the lock for a long create() call.
        token_count = self._count_tokens(system_prompt)
        if token_count < self.min_tokens:
            with self._lock:
                self._last_skipped = True
                # If we previously had a cache for a different prompt and now
                # fall below threshold, drop the old one to avoid drift.
                self._delete_current_locked()
                self._current_hash = prompt_hash
                self._current_expires_at = None
            self._record_metric(
                hit=False,
                extra_attributes={
                    **(dict(extra_attributes) if extra_attributes else {}),
                    "reason": "below_min_tokens",
                },
            )
            logger.info(
                f"[GeminiCache] Skipping explicit cache: prompt {token_count} tokens < min {self.min_tokens}"
            )
            return GeminiCacheResult(
                cached_content=None,
                hit=False,
                created=False,
                skipped_below_min=True,
                prompt_hash=prompt_hash,
            )

        # Cold path: create new cache. Build the system_instruction outside
        # the lock so a slow Vertex round-trip does not stall other threads.
        try:
            new_cache = self._build_cache(system_prompt)
        except Exception as exc:
            # Hard fail on Vertex side → fall back to implicit caching with
            # a logged warning. Better to keep serving than crash on infra.
            logger.warning(
                f"[GeminiCache] Failed to create explicit cache, falling back to implicit: {exc}"
            )
            self._record_metric(
                hit=False,
                extra_attributes={
                    **(dict(extra_attributes) if extra_attributes else {}),
                    "reason": "create_failed",
                },
            )
            return GeminiCacheResult(
                cached_content=None,
                hit=False,
                created=False,
                skipped_below_min=False,
                prompt_hash=prompt_hash,
            )

        with self._lock:
            # Another thread may have raced ahead and created its own. Prefer
            # the freshest one only if it is still valid; delete ours if we
            # lost the race against a non-expired sibling.
            if (
                self._current_hash == prompt_hash
                and self._current_cache is not None
                and not self._is_expired_locked()
            ):
                self._safe_delete(new_cache)
                self._record_metric(hit=True, extra_attributes=extra_attributes)
                return GeminiCacheResult(
                    cached_content=self._current_cache.resource_name,
                    hit=True,
                    created=False,
                    skipped_below_min=False,
                    prompt_hash=prompt_hash,
                )
            self._delete_current_locked()
            self._current_cache = new_cache
            self._current_hash = prompt_hash
            self._current_expires_at = self.clock() + self.ttl
            self._last_skipped = False

        self._record_metric(hit=False, extra_attributes=extra_attributes)
        logger.info(
            f"[GeminiCache] Created explicit cache {new_cache.resource_name} for hash {prompt_hash[:12]}"
        )
        return GeminiCacheResult(
            cached_content=new_cache.resource_name,
            hit=False,
            created=True,
            skipped_below_min=False,
            prompt_hash=prompt_hash,
        )

    def invalidate(self) -> bool:
        """Delete the current cache, if any. Returns ``True`` if deleted.

        Idempotent: calling twice is safe.
        """
        with self._lock:
            deleted = self._delete_current_locked()
            self._current_hash = None
            self._current_expires_at = None
            self._last_skipped = False
        return deleted

    def _is_expired_locked(self) -> bool:
        """Return ``True`` if the current cache TTL has elapsed (with skew).

        Lock must be held by caller. ``None`` expiry is treated as
        expired so a half-initialised state forces recreation.
        """
        if self._current_expires_at is None:
            return True
        return self.clock() + self.expiry_skew >= self._current_expires_at

    @property
    def current_hash(self) -> Optional[str]:
        return self._current_hash

    @property
    def current_resource_name(self) -> Optional[str]:
        cache = self._current_cache
        return cache.resource_name if cache is not None else None

    # ----- internal helpers -----

    def _compute_hash(self, system_prompt: str, tools_signature: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.model_name.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(system_prompt.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(tools_signature.encode("utf-8"))
        return hasher.hexdigest()

    def _count_tokens(self, text: str) -> int:
        counter = self.token_counter
        if counter is None:
            # ~4 chars/token heuristic — good enough for the min-tokens
            # threshold gate; production should inject the real counter.
            return max(0, len(text) // 4)
        try:
            return int(counter(text))
        except Exception as exc:
            logger.warning(
                f"[GeminiCache] token_counter raised, falling back to heuristic: {exc}"
            )
            return max(0, len(text) // 4)

    def _build_cache(self, system_prompt: str) -> _CachedContentLike:
        factory = self.cache_factory or _default_cache_factory
        return factory(
            model_name=self.model_name,
            system_instruction=system_prompt,
            ttl=self.ttl,
            display_name=self.display_name,
        )

    def _delete_current_locked(self) -> bool:
        """Delete ``self._current_cache``. Lock must be held by caller."""
        cache = self._current_cache
        if cache is None:
            return False
        self._safe_delete(cache)
        self._current_cache = None
        return True

    @staticmethod
    def _safe_delete(cache: _CachedContentLike) -> None:
        try:
            cache.delete()
        except Exception as exc:
            logger.warning(
                f"[GeminiCache] Failed to delete cache {getattr(cache, 'resource_name', '?')}: {exc}"
            )

    @staticmethod
    def _record_metric(
        *,
        hit: bool,
        extra_attributes: Optional[Mapping[str, str]] = None,
    ) -> None:
        meter = metrics.get_meter("engine.caching.gemini_cache")
        counter = meter.create_counter(
            name="gen_ai.cache.hit_count" if hit else "gen_ai.cache.miss_count",
            unit="{event}",
            description="GenAI explicit cache hit/miss counter.",
        )
        attrs: dict[str, str] = {}
        if extra_attributes:
            for key, value in extra_attributes.items():
                attrs[str(key)] = str(value)
        counter.add(1, attributes=attrs)


def _default_cache_factory(
    *,
    model_name: str,
    system_instruction: Optional[Any],
    ttl: timedelta,
    display_name: Optional[str] = None,
) -> _CachedContentLike:
    """Production cache factory using ``vertexai.caching.CachedContent``.

    Lazy-import so the module remains importable in test contexts where
    ``vertexai`` may not be initialised (no project / region configured).
    """
    from vertexai.caching import CachedContent  # type: ignore

    return CachedContent.create(  # type: ignore[no-any-return]
        model_name=model_name,
        system_instruction=system_instruction,
        ttl=ttl,
        display_name=display_name,
    )
