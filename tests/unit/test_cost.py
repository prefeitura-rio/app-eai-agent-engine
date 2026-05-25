"""Unit tests for ``engine.observability.cost``.

Coverage targets:
- Text-only cost matches the verified rate card.
- cache_read is a SUBSET of input (not additive) — the crux correctness rule.
- Cache reduces cost (never raises it) — guards against the double-count bug.
- reasoning is inside output (not billed separately).
- Audio input is priced higher than text.
- Cache storage adds cost proportional to token-hours.
- Unknown model raises UnknownModelError (fail-fast, not zero).
- Subset violations (cache_read>input, reasoning>output, negatives) raise.
- Zero usage is zero cost.
"""

from __future__ import annotations

import pytest

from engine.observability.cost import (
    RATE_CARD,
    Modality,
    ModelRates,
    TokenSubsetError,
    TokenUsage,
    UnknownModalityError,
    UnknownModelError,
    compute_cost_usd,
    supported_models,
)

MODEL = "gemini-2.5-flash"


def test_text_only_cost_matches_rate_card():
    # 1M input (no cache) + 1M output, text.
    usage = TokenUsage(input=1_000_000, output=1_000_000)
    cost = compute_cost_usd(usage, MODEL, Modality.TEXT)
    # 1M × $0.30 + 1M × $2.50 = $2.80
    assert cost == pytest.approx(0.30 + 2.50)


def test_cache_read_is_subset_not_additive():
    """The crux: input INCLUDES cache_read. 1M input where 0.4M was cached
    bills 0.6M at full + 0.4M at cached — NOT 1M full + 0.4M cached."""

    usage = TokenUsage(input=1_000_000, output=0, cache_read=400_000)
    cost = compute_cost_usd(usage, MODEL, Modality.TEXT)
    # (1M - 0.4M) × $0.30 + 0.4M × $0.03 = 0.6×0.30 + 0.4×0.03 = 0.18 + 0.012
    assert cost == pytest.approx(0.18 + 0.012)


def test_cache_reduces_cost_never_raises_it():
    """Regression guard for the double-count bug: more cache_read (same
    total input) must LOWER cost, because cached tokens are cheaper."""

    no_cache = compute_cost_usd(
        TokenUsage(input=1_000_000, output=0, cache_read=0), MODEL
    )
    half_cached = compute_cost_usd(
        TokenUsage(input=1_000_000, output=0, cache_read=500_000), MODEL
    )
    full_cached = compute_cost_usd(
        TokenUsage(input=1_000_000, output=0, cache_read=1_000_000), MODEL
    )
    assert full_cached < half_cached < no_cache


def test_reasoning_inside_output_not_billed_separately():
    """reasoning ⊆ output: two usages with same output but different
    reasoning split cost the same (reasoning isn't a separate term)."""

    low_reasoning = compute_cost_usd(
        TokenUsage(input=0, output=1_000_000, reasoning=100_000), MODEL
    )
    high_reasoning = compute_cost_usd(
        TokenUsage(input=0, output=1_000_000, reasoning=900_000), MODEL
    )
    assert low_reasoning == high_reasoning == pytest.approx(2.50)


def test_audio_input_costs_more_than_text():
    usage = TokenUsage(input=1_000_000, output=0)
    text_cost = compute_cost_usd(usage, MODEL, Modality.TEXT)
    audio_cost = compute_cost_usd(usage, MODEL, Modality.AUDIO)
    assert audio_cost == pytest.approx(1.00)
    assert text_cost == pytest.approx(0.30)
    assert audio_cost > text_cost


def test_audio_cached_rate():
    # 1M input fully cached, audio: 1M × $0.10
    usage = TokenUsage(input=1_000_000, output=0, cache_read=1_000_000)
    cost = compute_cost_usd(usage, MODEL, Modality.AUDIO)
    assert cost == pytest.approx(0.10)


def test_cache_storage_adds_cost():
    base = compute_cost_usd(TokenUsage(input=0, output=0), MODEL)
    with_storage = compute_cost_usd(
        TokenUsage(input=0, output=0, cache_storage_token_hours=2_000_000.0), MODEL
    )
    # 2M token-hours × $1.00/1M/hr = $2.00
    assert base == 0.0
    assert with_storage == pytest.approx(2.00)


def test_negative_cache_storage_raises():
    """Storage is an independent float (no subset bound) — a negative value
    would drive cost negative and silently underreport. Must fail fast."""

    with pytest.raises(TokenSubsetError, match="cache_storage_token_hours"):
        compute_cost_usd(
            TokenUsage(input=0, output=0, cache_storage_token_hours=-1_000_000.0),
            MODEL,
        )


def test_unknown_model_raises():
    with pytest.raises(UnknownModelError, match="rate card"):
        compute_cost_usd(TokenUsage(input=100, output=100), "gemini-9.9-imaginary")


def test_zero_usage_is_zero_cost():
    assert compute_cost_usd(TokenUsage(input=0, output=0), MODEL) == 0.0


@pytest.mark.parametrize(
    "usage",
    [
        TokenUsage(input=100, output=0, cache_read=200),  # cache_read > input
        TokenUsage(input=-1, output=0),  # negative input → cache_read(0) ok but...
        TokenUsage(input=100, output=0, cache_read=-5),  # negative cache_read
    ],
)
def test_cache_read_subset_violation_raises(usage):
    with pytest.raises(TokenSubsetError, match="cache_read"):
        compute_cost_usd(usage, MODEL)


@pytest.mark.parametrize(
    "usage",
    [
        TokenUsage(input=0, output=100, reasoning=200),  # reasoning > output
        TokenUsage(input=0, output=100, reasoning=-5),  # negative reasoning
    ],
)
def test_reasoning_subset_violation_raises(usage):
    with pytest.raises(TokenSubsetError, match="reasoning"):
        compute_cost_usd(usage, MODEL)


def test_unsupported_modality_for_known_model_raises(monkeypatch):
    """A model with a partial rate card (missing a modality) must raise a
    typed UnknownModalityError, not a raw KeyError."""

    text_only = ModelRates(
        input_per_modality={Modality.TEXT: 0.30},
        cached_per_modality={Modality.TEXT: 0.03},
        output=2.50,
        cache_storage_per_hour=1.00,
    )
    monkeypatch.setitem(RATE_CARD, "text-only-model", text_only)
    with pytest.raises(UnknownModalityError, match="modality"):
        compute_cost_usd(
            TokenUsage(input=100, output=100), "text-only-model", Modality.AUDIO
        )


def test_supported_models_lists_rate_card():
    assert supported_models() == tuple(sorted(RATE_CARD))
    assert MODEL in supported_models()


def test_realistic_mixed_request():
    """A realistic turn: 8k input (3k cached), 1.2k output (400 reasoning), text."""

    usage = TokenUsage(
        input=8_000, output=1_200, cache_read=3_000, reasoning=400
    )
    cost = compute_cost_usd(usage, MODEL, Modality.TEXT)
    expected = (
        (8_000 - 3_000) * 0.30  # non-cached input
        + 3_000 * 0.03          # cached input
        + 1_200 * 2.50          # output (reasoning included)
    ) / 1_000_000
    assert cost == pytest.approx(expected)
