"""Engine active learning wiring (Iter 2.5 of plano-bot-2026-loop-v2).

Submodules:
- flag_client: low-privilege HTTP client for Gateway /api/v1/flags/:name/assign.
- fewshot_injector: pure renderer for treatment-variant few-shot SystemMessage.
"""

from engine.active_learning.fewshot_injector import (
    FewShotExample,
    build_few_shot_message,
    render_few_shot_block,
)
from engine.active_learning.flag_client import (
    FlagAssignment,
    FlagClient,
    FlagClientError,
    FlagClientTimeout,
)

__all__ = [
    "FewShotExample",
    "FlagAssignment",
    "FlagClient",
    "FlagClientError",
    "FlagClientTimeout",
    "build_few_shot_message",
    "render_few_shot_block",
]
