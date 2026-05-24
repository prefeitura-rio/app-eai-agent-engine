"""Engine active learning wiring (Iter 2.5 of plano-bot-2026-loop-v2).

Submodules:
- flag_client: low-privilege HTTP client for Gateway /api/v1/flags/:name/assign.
"""

from engine.active_learning.flag_client import (
    FlagAssignment,
    FlagClient,
    FlagClientError,
    FlagClientTimeout,
)

__all__ = [
    "FlagAssignment",
    "FlagClient",
    "FlagClientError",
    "FlagClientTimeout",
]
