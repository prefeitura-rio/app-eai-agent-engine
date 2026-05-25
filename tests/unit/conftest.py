"""Shared test fixtures for the unit suite.

OTel's global ``MeterProvider`` is process-global and set-once: the SDK
refuses to re-assign it after the first ``set_meter_provider`` call. So any
metric test that installs its own provider collides with every other metric
test module depending on collection order. This fixture is the SINGLE place
the suite installs a provider — both ``test_token_metrics`` and
``test_cost_metrics`` (and any future metric test) share it.
"""

from __future__ import annotations

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import Histogram as SdkHistogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
)


@pytest.fixture(scope="session")
def shared_metric_reader() -> InMemoryMetricReader:
    """Session-scoped InMemoryMetricReader behind the one global MeterProvider.

    DELTA temporality means ``get_metrics_data()`` drains cumulative state, so
    a test that drains at start sees only its own observations. Each metric
    test module's per-test fixture is responsible for draining + resetting its
    module-cached instrument.
    """

    reader = InMemoryMetricReader(
        preferred_temporality={SdkHistogram: AggregationTemporality.DELTA},
    )
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return reader
