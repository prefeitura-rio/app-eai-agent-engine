"""Engine active learning wiring (Iter 2.5 of plano-bot-2026-loop-v2).

Submodules:
- flag_client: low-privilege HTTP client for Gateway /api/v1/flags/:name/assign.
- fewshot_injector: pure renderer for treatment-variant few-shot SystemMessage.
- embedder: Gemini text-embedding-004 adapter implementing the Embedder Protocol.
- hook: pure orchestrator that combines assignment + examples into state.
"""

from engine.active_learning.embedder import (
    Embedder,
    GeminiEmbedder,
    GeminiEmbedderConfig,
    GeminiEmbedderError,
)
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
from engine.active_learning.hook import (
    TREATMENT_VARIANT,
    inject_few_shot_examples,
)
from engine.active_learning.resolver import (
    ActiveLearningResolver,
    FewShotRetriever,
    NullRetriever,
    ResolvedActiveLearning,
)

__all__ = [
    "ActiveLearningResolver",
    "Embedder",
    "FewShotExample",
    "FewShotRetriever",
    "FlagAssignment",
    "FlagClient",
    "FlagClientError",
    "FlagClientTimeout",
    "GeminiEmbedder",
    "GeminiEmbedderConfig",
    "GeminiEmbedderError",
    "NullRetriever",
    "ResolvedActiveLearning",
    "TREATMENT_VARIANT",
    "build_few_shot_message",
    "inject_few_shot_examples",
    "render_few_shot_block",
]
