"""Gemini explicit cache management for the Engine.

Submodules:
- gemini_cache: ``GeminiCacheManager`` — creates/refreshes/deletes the
  Vertex AI ``CachedContent`` resource holding the system prompt so
  subsequent requests pay only the discounted cache-read price.
"""

from engine.caching.gemini_cache import (
    GEMINI_EXPLICIT_CACHE_MIN_TOKENS,
    GeminiCacheManager,
    GeminiCacheResult,
)

__all__ = [
    "GEMINI_EXPLICIT_CACHE_MIN_TOKENS",
    "GeminiCacheManager",
    "GeminiCacheResult",
]
