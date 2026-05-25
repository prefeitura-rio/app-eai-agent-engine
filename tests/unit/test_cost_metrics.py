"""Unit tests for ``engine.observability.cost_metrics``.

Validates that ``record_cost_usd`` records on the configured MeterProvider
with the right attributes + value, that unknown model / subset violations
are skipped (never raised), and that the text-only scope is tagged.

Uses an in-memory MeterProvider with an InMemoryMetricReader (same harness
shape as test_token_metrics).
"""

from __future__ import annotations

from typing import Iterator

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from engine.observability.cost import Modality, TokenUsage
from engine.observability.cost_metrics import (
    ATTR_COST_SCOPE,
    SCOPE_TEXT_ONLY,
    record_cost_usd,
    reset_cost_metrics_for_testing,
)
from engine.observability.token_metrics import (
    ATTR_OPERATION_NAME,
    ATTR_REQUEST_MODEL,
    ATTR_THREAD_ID,
)

TEST_MODEL = "gemini-2.5-flash"
TEST_THREAD = "thread-xyz"
COST_INSTRUMENT = "gen_ai.client.cost.usd"


@pytest.fixture
def reader(shared_metric_reader: InMemoryMetricReader) -> Iterator[InMemoryMetricReader]:
    shared_metric_reader.get_metrics_data()  # drain residual from prior tests
    reset_cost_metrics_for_testing()
    try:
        yield shared_metric_reader
    finally:
        reset_cost_metrics_for_testing()


def _points(reader: InMemoryMetricReader):
    data = reader.get_metrics_data()
    if data is None:
        return []
    points = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == COST_INSTRUMENT:
                    points.extend(metric.data.data_points)
    return points


def test_records_cost_with_expected_attributes(reader):
    # 1M input + 1M output text = $2.80
    returned = record_cost_usd(
        TokenUsage(input=1_000_000, output=1_000_000),
        model=TEST_MODEL,
        thread_id=TEST_THREAD,
    )
    assert returned == pytest.approx(2.80)
    points = _points(reader)
    assert len(points) == 1
    attrs = dict(points[0].attributes)
    assert attrs[ATTR_REQUEST_MODEL] == TEST_MODEL
    assert attrs[ATTR_THREAD_ID] == TEST_THREAD
    assert attrs[ATTR_COST_SCOPE] == SCOPE_TEXT_ONLY
    assert attrs[ATTR_OPERATION_NAME] == "chat"
    # Histogram sum equals the recorded cost.
    assert points[0].sum == pytest.approx(2.80)


def test_text_only_scope_tag_present(reader):
    record_cost_usd(TokenUsage(input=1000, output=500), model=TEST_MODEL)
    attrs = dict(_points(reader)[0].attributes)
    assert attrs[ATTR_COST_SCOPE] == SCOPE_TEXT_ONLY


def test_audio_modality_tags_scope_audio(reader):
    record_cost_usd(
        TokenUsage(input=1000, output=500),
        model=TEST_MODEL,
        modality=Modality.AUDIO,
    )
    attrs = dict(_points(reader)[0].attributes)
    assert attrs[ATTR_COST_SCOPE] == Modality.AUDIO.value


def test_unknown_model_skips_emission_returns_none(reader):
    returned = record_cost_usd(
        TokenUsage(input=100, output=100), model="gemini-imaginary-9"
    )
    assert returned is None
    assert _points(reader) == []  # nothing emitted


def test_subset_violation_skips_emission_returns_none(reader):
    # cache_read > input → cost.py raises TokenSubsetError → skipped
    returned = record_cost_usd(
        TokenUsage(input=100, output=0, cache_read=500), model=TEST_MODEL
    )
    assert returned is None
    assert _points(reader) == []


def test_thread_id_omitted_when_absent(reader):
    record_cost_usd(TokenUsage(input=1000, output=500), model=TEST_MODEL)
    attrs = dict(_points(reader)[0].attributes)
    assert ATTR_THREAD_ID not in attrs


def test_string_modality_is_coerced_not_raised(reader):
    """A str-enum lets a plain string slip through compute_cost_usd; the
    wrapper must coerce it (not raise AttributeError on .value)."""

    returned = record_cost_usd(
        TokenUsage(input=1000, output=500), model=TEST_MODEL, modality="text"
    )
    assert returned is not None
    attrs = dict(_points(reader)[0].attributes)
    assert attrs[ATTR_COST_SCOPE] == SCOPE_TEXT_ONLY


def test_invalid_modality_string_skips_returns_none(reader):
    returned = record_cost_usd(
        TokenUsage(input=1000, output=500), model=TEST_MODEL, modality="hologram"
    )
    assert returned is None
    assert _points(reader) == []


def test_emission_failure_is_swallowed_returns_none(reader, monkeypatch):
    """Honors the never-raises contract standalone: if the histogram record
    throws (e.g. misconfigured provider), record_cost_usd returns None and
    does not propagate — the citizen turn must not break."""

    class _BoomHistogram:
        def record(self, *args, **kwargs):
            raise RuntimeError("simulated OTel failure")

    monkeypatch.setattr(
        "engine.observability.cost_metrics._get_histogram", lambda: _BoomHistogram()
    )
    # Must NOT raise.
    returned = record_cost_usd(TokenUsage(input=1000, output=500), model=TEST_MODEL)
    assert returned is None


def test_cache_lowers_recorded_cost(reader):
    """End-to-end: a cached request records less cost than an uncached one
    (the subset-correct formula flows through to the metric)."""

    uncached = record_cost_usd(
        TokenUsage(input=1_000_000, output=0, cache_read=0), model=TEST_MODEL
    )
    cached = record_cost_usd(
        TokenUsage(input=1_000_000, output=0, cache_read=1_000_000),
        model=TEST_MODEL,
    )
    assert cached < uncached
