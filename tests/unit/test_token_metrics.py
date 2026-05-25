"""Unit tests for ``engine.observability.token_metrics``.

Goal: validate that ``record_token_usage`` records on the configured
``MeterProvider`` with the correct GenAI SemConv v1.37 attributes, that
non-positive counts are dropped, and that the global SDK is restored
between tests (no leak).

We install an in-memory ``MeterProvider`` with an
``InMemoryMetricReader`` so assertions can read recorded histogram points
without an OTLP backend.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from engine.observability.token_metrics import (
    ATTR_OPERATION_NAME,
    ATTR_REQUEST_MODEL,
    ATTR_THREAD_ID,
    ATTR_TOKEN_TYPE,
    OPERATION_NAME_CHAT,
    TOKEN_TYPE_CACHE_READ,
    TOKEN_TYPE_INPUT,
    TOKEN_TYPE_OUTPUT,
    TOKEN_TYPE_REASONING,
    record_token_usage,
    reset_token_metrics_for_testing,
)


# Sentinel test values
TEST_MODEL = "gemini-2.5-flash"
TEST_THREAD = "thread-abc"


# The global ``MeterProvider`` is installed once for the whole unit suite by
# the ``shared_metric_reader`` fixture in conftest.py (OTel refuses to
# re-assign the global provider, so every metric test module must share one).


@pytest.fixture
def in_memory_meter_provider(
    shared_metric_reader: InMemoryMetricReader,
) -> Iterator[InMemoryMetricReader]:
    """Yield the shared session reader, draining any prior observations.

    DELTA temporality + draining at start means each test sees only the points
    it records; the module-cached histogram is reset so it rebinds to the
    shared global provider.
    """
    shared_metric_reader.get_metrics_data()
    reset_token_metrics_for_testing()
    try:
        yield shared_metric_reader
    finally:
        reset_token_metrics_for_testing()


def _collect_data_points(reader: InMemoryMetricReader, instrument_name: str):
    """Drain the reader and return all data points for ``instrument_name``."""
    metrics_data = reader.get_metrics_data()
    if metrics_data is None:
        return []
    points = []
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == instrument_name:
                    points.extend(metric.data.data_points)
    return points


def _attrs_for(reader: InMemoryMetricReader, instrument_name: str):
    return [dict(point.attributes) for point in _collect_data_points(reader, instrument_name)]


def test_records_input_token_with_expected_attributes(in_memory_meter_provider):
    record_token_usage(
        TOKEN_TYPE_INPUT,
        1234,
        model=TEST_MODEL,
        thread_id=TEST_THREAD,
    )
    attrs_list = _attrs_for(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert len(attrs_list) == 1
    attrs = attrs_list[0]
    assert attrs[ATTR_TOKEN_TYPE] == TOKEN_TYPE_INPUT
    assert attrs[ATTR_REQUEST_MODEL] == TEST_MODEL
    assert attrs[ATTR_OPERATION_NAME] == OPERATION_NAME_CHAT
    assert attrs[ATTR_THREAD_ID] == TEST_THREAD


def test_records_output_token(in_memory_meter_provider):
    record_token_usage(TOKEN_TYPE_OUTPUT, 256, model=TEST_MODEL)
    attrs_list = _attrs_for(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert len(attrs_list) == 1
    assert attrs_list[0][ATTR_TOKEN_TYPE] == TOKEN_TYPE_OUTPUT
    # No thread id was provided → attribute must not appear at all.
    assert ATTR_THREAD_ID not in attrs_list[0]


def test_records_cache_read_and_reasoning_separately(in_memory_meter_provider):
    record_token_usage(TOKEN_TYPE_INPUT, 100, model=TEST_MODEL, thread_id=TEST_THREAD)
    record_token_usage(TOKEN_TYPE_OUTPUT, 50, model=TEST_MODEL, thread_id=TEST_THREAD)
    record_token_usage(TOKEN_TYPE_CACHE_READ, 70, model=TEST_MODEL, thread_id=TEST_THREAD)
    record_token_usage(TOKEN_TYPE_REASONING, 10, model=TEST_MODEL, thread_id=TEST_THREAD)
    attrs_list = _attrs_for(in_memory_meter_provider, "gen_ai.client.token.usage")
    types = sorted(attr[ATTR_TOKEN_TYPE] for attr in attrs_list)
    assert types == [
        TOKEN_TYPE_CACHE_READ,
        TOKEN_TYPE_INPUT,
        TOKEN_TYPE_OUTPUT,
        TOKEN_TYPE_REASONING,
    ]


def test_non_positive_counts_are_dropped(in_memory_meter_provider):
    record_token_usage(TOKEN_TYPE_INPUT, 0, model=TEST_MODEL)
    record_token_usage(TOKEN_TYPE_INPUT, -5, model=TEST_MODEL)
    record_token_usage(TOKEN_TYPE_INPUT, "not an int", model=TEST_MODEL)  # type: ignore[arg-type]
    points = _collect_data_points(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert points == []


def test_string_count_coerced(in_memory_meter_provider):
    """If a caller passes a numeric string we accept it (defensive)."""
    record_token_usage(TOKEN_TYPE_INPUT, "42", model=TEST_MODEL)  # type: ignore[arg-type]
    points = _collect_data_points(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert len(points) == 1
    assert points[0].sum == 42


def test_extra_attributes_override_defaults(in_memory_meter_provider):
    record_token_usage(
        TOKEN_TYPE_INPUT,
        10,
        model=TEST_MODEL,
        thread_id=TEST_THREAD,
        extra_attributes={"deployment.env": "staging"},
    )
    attrs_list = _attrs_for(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert len(attrs_list) == 1
    assert attrs_list[0]["deployment.env"] == "staging"
    assert attrs_list[0][ATTR_TOKEN_TYPE] == TOKEN_TYPE_INPUT


def test_histogram_records_count_in_sum(in_memory_meter_provider):
    record_token_usage(TOKEN_TYPE_INPUT, 1000, model=TEST_MODEL)
    record_token_usage(TOKEN_TYPE_INPUT, 500, model=TEST_MODEL)
    points = _collect_data_points(in_memory_meter_provider, "gen_ai.client.token.usage")
    # Same dimension key (TOKEN_TYPE_INPUT / model only) → one aggregated point.
    assert len(points) == 1
    assert points[0].count == 2
    assert points[0].sum == 1500


def test_call_never_raises_on_malformed_extra_attrs(in_memory_meter_provider):
    """Defensive: caller-side keys/values that cannot be stringified gracefully
    must not crash the recording path (the histogram swallows or rejects them).
    """
    # The SDK accepts only str keys; we coerce above. Recording must succeed.
    record_token_usage(
        TOKEN_TYPE_INPUT,
        10,
        model=TEST_MODEL,
        extra_attributes={"intval": 5, "boolval": True},  # type: ignore[dict-item]
    )
    points = _collect_data_points(in_memory_meter_provider, "gen_ai.client.token.usage")
    assert len(points) == 1
