"""Pure cost calculation for Gemini token usage (Iter 4 Phase B Tier 1).

Encodes the verified Gemini pricing rate card (per model, per modality) and
computes USD cost from the token counts that ``token_metrics`` already emits
(``input`` / ``output`` / ``cache_read`` / ``reasoning``).

CRITICAL correctness rule (Vertex telemetry semantics)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verified against ``langchain-google-vertexai`` 2.1.2
``_get_usage_metadata_gemini`` (the version the Engine pins):

- ``input`` = ``prompt_token_count``, which INCLUDES the ``cache_read``
  (``cached_content_token_count``) subset → **cache_read ⊆ input**.
- ``output`` = ``candidates_token_count`` — the VISIBLE answer ONLY. It
  does NOT include reasoning.
- ``reasoning`` = ``thoughts_token_count`` is reported SEPARATELY and is
  **additive** (``prompt + candidates + thoughts == total``) →
  **reasoning is NOT a subset of output**.

Reasoning (thinking) tokens are billed at the output rate (Google prices
output "including thinking tokens"). So the correct cost is::

    (input - cache_read)  * rate_input        # non-cached input at full rate
  + cache_read            * rate_cached        # cached input at the discounted rate
  + (output + reasoning)  * rate_output        # visible + thinking, both output-priced
  + cache_storage_token_hours * rate_storage

Two traps this module guards against:
1. Double-counting the cached portion (it is *inside* input) — subtract it.
2. Dropping or under-billing thinking-heavy turns: an earlier version
   treated reasoning as ⊆ output and rejected ``reasoning > output``, which
   silently dropped the cost of exactly the most expensive (thinking-heavy)
   turns. reasoning is additive and only requires ``reasoning ≥ 0``.

Modality
~~~~~~~~
Input and cache-read rates differ by modality (audio input is ~3.3× text on
Gemini 2.5 Flash). Output is priced uniformly regardless of modality. The
caller supplies the modality; until the telemetry carries a modality
dimension (Iter 4 Phase B instrumentation decision), callers default to
``TEXT`` and accept a declared error for audio-heavy traffic.

Rate card
~~~~~~~~~
Verified 2026-05-25 against https://ai.google.dev/gemini-api/docs/pricing
(official Google page; preferred over third-party summaries). Prices are USD
per 1M tokens. Rates drift — re-verify on model migration. Unknown models
raise ``UnknownModelError`` (fail-fast) rather than pricing at zero.

This module is pure: no I/O, no telemetry, no clock. ``float`` is used (not
``Decimal``) because the output feeds a cost *dashboard* reconciled to ±5%
against billing, not a transactional ledger — float error (~1e-15) is
irrelevant at that tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from engine.observability.token_metrics import (
    TOKEN_TYPE_CACHE_READ,
    TOKEN_TYPE_INPUT,
    TOKEN_TYPE_OUTPUT,
    TOKEN_TYPE_REASONING,
)

TOKENS_PER_MILLION: Final[float] = 1_000_000.0
RATE_CARD_VERIFIED_DATE: Final[str] = "2026-05-25"


class Modality(str, Enum):
    """Input modality. Image/video share the text rate on Gemini 2.5 Flash;
    audio is priced higher. Output rate is modality-independent."""

    TEXT = "text"
    AUDIO = "audio"


class UnknownModelError(Exception):
    """Raised when a model has no entry in the rate card (fail-fast — never
    silently price an unknown model at zero)."""


class UnknownModalityError(Exception):
    """Raised when a known model has no rate for the requested modality
    (fail-fast — closes the raw-KeyError path for partial rate cards)."""


class TokenSubsetError(Exception):
    """Raised when token counts violate the documented invariants
    (cache_read ⊆ input; output, reasoning, cache_storage ≥ 0) — signals
    telemetry corruption or a caller bug."""


@dataclass(frozen=True)
class ModelRates:
    """USD-per-1M-token rates for one model.

    ``input``/``cached`` are keyed by modality (text vs audio). ``output``
    is a single rate (modality-independent). ``cache_storage_per_hour`` is
    USD per 1M cached tokens held for one hour.
    """

    input_per_modality: dict[Modality, float]
    cached_per_modality: dict[Modality, float]
    output: float
    cache_storage_per_hour: float


# Gemini 2.5 Flash (Standard, Paid Tier) — verified 2026-05-25.
# input: text/image/video $0.30, audio $1.00 | output (incl thinking) $2.50
# cached: text/image/video $0.03, audio $0.10 | cache storage $1.00/1M/hour
_GEMINI_2_5_FLASH = ModelRates(
    input_per_modality={Modality.TEXT: 0.30, Modality.AUDIO: 1.00},
    cached_per_modality={Modality.TEXT: 0.03, Modality.AUDIO: 0.10},
    output=2.50,
    cache_storage_per_hour=1.00,
)

RATE_CARD: Final[dict[str, ModelRates]] = {
    "gemini-2.5-flash": _GEMINI_2_5_FLASH,
}


@dataclass(frozen=True)
class TokenUsage:
    """Token counts for one request, mirroring the ``gen_ai.token.type``
    dimensions emitted by ``token_metrics``.

    Invariants (enforced by ``compute_cost_usd``):
    - ``cache_read`` ⊆ ``input`` (0 ≤ cache_read ≤ input)
    - ``output`` ≥ 0 (visible answer / candidates tokens)
    - ``reasoning`` ≥ 0 (thinking tokens; ADDITIVE to output, not a subset —
      billed at the output rate)
    - ``cache_storage_token_hours`` ≥ 0
    """

    input: int
    output: int
    cache_read: int = 0
    reasoning: int = 0
    cache_storage_token_hours: float = 0.0


def compute_cost_usd(
    usage: TokenUsage,
    model: str,
    modality: Modality = Modality.TEXT,
) -> float:
    """Return the USD cost of ``usage`` for ``model`` at ``modality``.

    Raises:
        UnknownModelError: ``model`` is not in the rate card.
        TokenSubsetError: token counts violate the subset invariants.

    Notes:
        ``reasoning`` (thinking) tokens are ADDITIVE to ``output`` (the
        candidates count excludes them in langchain-google-vertexai) and are
        billed at the output rate, so the billable output is
        ``output + reasoning``. Validated as ``reasoning ≥ 0`` — it is NOT
        bounded by ``output``.
    """

    rates = RATE_CARD.get(model)
    if rates is None:
        raise UnknownModelError(
            f"No rate card entry for model {model!r} "
            f"(rate card verified {RATE_CARD_VERIFIED_DATE}); add an entry "
            "before computing cost for this model."
        )

    if usage.cache_read < 0 or usage.cache_read > usage.input:
        raise TokenSubsetError(
            f"cache_read ({usage.cache_read}) must be in [0, input "
            f"({usage.input})] — cache_read ⊆ input violated"
        )
    if usage.output < 0:
        raise TokenSubsetError(f"output ({usage.output}) must be ≥ 0")
    # reasoning is ADDITIVE to output (not a subset) — only ≥ 0 is required.
    # The earlier reasoning ≤ output check silently dropped thinking-heavy
    # turns (reasoning can exceed the visible candidates count).
    if usage.reasoning < 0:
        raise TokenSubsetError(f"reasoning ({usage.reasoning}) must be ≥ 0")
    # Storage is an independent float (no subset bound), so unlike the token
    # terms it can drive cost negative if a caller derives token-hours from a
    # reversed/buggy interval. Guard explicitly — fail fast, never underreport.
    if usage.cache_storage_token_hours < 0:
        raise TokenSubsetError(
            f"cache_storage_token_hours ({usage.cache_storage_token_hours}) "
            "must be ≥ 0"
        )

    if (
        modality not in rates.input_per_modality
        or modality not in rates.cached_per_modality
    ):
        raise UnknownModalityError(
            f"Model {model!r} has no rate for modality {modality.value!r} "
            f"(rate card verified {RATE_CARD_VERIFIED_DATE})"
        )
    rate_input = rates.input_per_modality[modality]
    rate_cached = rates.cached_per_modality[modality]

    non_cached_input = usage.input - usage.cache_read
    # Visible (candidates) + thinking (reasoning) tokens are both output-priced.
    billable_output = usage.output + usage.reasoning
    cost_per_million = (
        non_cached_input * rate_input
        + usage.cache_read * rate_cached
        + billable_output * rates.output
        + usage.cache_storage_token_hours * rates.cache_storage_per_hour
    )
    return cost_per_million / TOKENS_PER_MILLION


def supported_models() -> tuple[str, ...]:
    """Return the models with a rate-card entry (sorted)."""

    return tuple(sorted(RATE_CARD))


# Re-export the token-type vocabulary so callers mapping raw telemetry rows
# into TokenUsage use the same canonical strings as the emitter.
__all__ = [
    "Modality",
    "ModelRates",
    "RATE_CARD",
    "RATE_CARD_VERIFIED_DATE",
    "TokenSubsetError",
    "TokenUsage",
    "UnknownModalityError",
    "UnknownModelError",
    "compute_cost_usd",
    "supported_models",
    "TOKEN_TYPE_INPUT",
    "TOKEN_TYPE_OUTPUT",
    "TOKEN_TYPE_CACHE_READ",
    "TOKEN_TYPE_REASONING",
]
