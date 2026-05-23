"""Engine middleware (cross-cutting transforms applied to messages).

Submodules:
- pii_redaction: PT-BR PII redaction / restore before/after external LLM calls.
"""

from engine.middleware.pii_redaction import (
    PIIRedactor,
    redact,
    restore,
)

__all__ = [
    "PIIRedactor",
    "redact",
    "restore",
]
