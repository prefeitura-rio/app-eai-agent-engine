"""Engine middleware (cross-cutting transforms applied to messages).

Submodules:
- pii_redaction: PT-BR PII redaction / restore before/after external LLM calls.
"""

from engine.middleware.pii_redaction import (
    PIIRedactor,
    PIIThreadCache,
    redact,
    redact_with_cache,
    restore,
    restore_with_cache,
    text_contains_token,
)

__all__ = [
    "PIIRedactor",
    "PIIThreadCache",
    "redact",
    "redact_with_cache",
    "restore",
    "restore_with_cache",
    "text_contains_token",
]
