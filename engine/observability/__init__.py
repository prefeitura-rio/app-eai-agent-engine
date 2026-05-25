"""Observability primitives for the Engine (OTel metrics, tracing helpers).

Submodules:
- token_metrics: GenAI SemConv v1.37 histogram ``gen_ai.client.token.usage``
- cost: pure USD cost calculation from token usage (Iter 4 Phase B Tier 1)
"""

from engine.observability.cost import (
    Modality,
    TokenSubsetError,
    TokenUsage,
    UnknownModelError,
    compute_cost_usd,
    supported_models,
)
from engine.observability.token_metrics import (
    TOKEN_TYPE_CACHE_READ,
    TOKEN_TYPE_INPUT,
    TOKEN_TYPE_OUTPUT,
    TOKEN_TYPE_REASONING,
    record_token_usage,
    reset_token_metrics_for_testing,
)

__all__ = [
    "Modality",
    "TOKEN_TYPE_CACHE_READ",
    "TOKEN_TYPE_INPUT",
    "TOKEN_TYPE_OUTPUT",
    "TOKEN_TYPE_REASONING",
    "TokenSubsetError",
    "TokenUsage",
    "UnknownModelError",
    "compute_cost_usd",
    "record_token_usage",
    "reset_token_metrics_for_testing",
    "supported_models",
]
