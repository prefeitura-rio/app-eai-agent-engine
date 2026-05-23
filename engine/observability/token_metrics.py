"""OpenTelemetry GenAI token-usage histogram.

Emits ``gen_ai.client.token.usage`` (OTel GenAI SemConv v1.37, still in
"experimental" status as of 2026-05) so per-request cost is observable in
Datadog / Grafana / Honeycomb / any OTLP-aware backend.

Why this exists
---------------
The Engine already logs rich token breakdowns through ``loguru`` in
``Agent._log_token_usage`` (system prompt, memory, conversation, tools,
cache_read, reasoning). Logs are great for incident archaeology but cannot
drive dashboards, SLOs or alerting on per-token cost. A histogram metric
filtered by ``gen_ai.token.type`` covers that gap.

Reference: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/

Public API
~~~~~~~~~~
- ``record_token_usage(token_type, count, attributes=...)`` — record one
  histogram observation. Safe to call before OTel is set up (we resolve the
  meter lazily through the global ``MeterProvider``); if the SDK is not
  configured the call is a no-op.
- ``TOKEN_TYPE_*`` — canonical values for the ``gen_ai.token.type``
  dimension. The SemConv vocabulary includes ``input`` and ``output``;
  Gemini surfaces ``cache_read`` and ``reasoning`` separately so we add
  them as project-local extensions.
- ``reset_token_metrics_for_testing()`` — test seam to drop the cached
  histogram so a fresh ``MeterProvider`` can be installed between tests.

This module is intentionally **side-effect free at import time**: it does
not touch the global ``MeterProvider`` until ``record_token_usage`` is
called for the first time.
"""

from __future__ import annotations

import threading
from typing import Mapping, Optional

from opentelemetry import metrics
from opentelemetry.metrics import Histogram, Meter

# GenAI SemConv v1.37 attribute keys
ATTR_TOKEN_TYPE: str = "gen_ai.token.type"
ATTR_REQUEST_MODEL: str = "gen_ai.request.model"
ATTR_OPERATION_NAME: str = "gen_ai.operation.name"
ATTR_THREAD_ID: str = "thread.id"

# Canonical token type vocabulary (input/output from SemConv; cache_read &
# reasoning are project-local extensions matching the loguru breakdown the
# Engine already emits).
TOKEN_TYPE_INPUT: str = "input"
TOKEN_TYPE_OUTPUT: str = "output"
TOKEN_TYPE_CACHE_READ: str = "cache_read"
TOKEN_TYPE_REASONING: str = "reasoning"

# GenAI SemConv v1.37 operation value for chat completions
OPERATION_NAME_CHAT: str = "chat"

# Instrument name follows GenAI SemConv v1.37
_HISTOGRAM_NAME: str = "gen_ai.client.token.usage"
_HISTOGRAM_DESCRIPTION: str = (
    "Number of tokens used in GenAI requests. Dimensions: gen_ai.token.type "
    "(input|output|cache_read|reasoning), gen_ai.request.model, "
    "gen_ai.operation.name, thread.id."
)
_HISTOGRAM_UNIT: str = "{token}"
_INSTRUMENTATION_SCOPE: str = "engine.observability.token_metrics"

# Lazy singleton — populated on first use; reset_token_metrics_for_testing()
# can clear it so tests can wire fresh MeterProviders.
_lock = threading.Lock()
_histogram: Optional[Histogram] = None


def _get_histogram() -> Histogram:
    """Resolve the token usage histogram lazily.

    We delay reading from the global ``MeterProvider`` until the first
    ``record_token_usage`` call so import order does not constrain when
    OTel is configured. If the SDK is not installed/configured, the API's
    ``NoOpMeterProvider`` returns no-op instruments and recording becomes
    a silent no-op.
    """
    global _histogram
    if _histogram is not None:
        return _histogram
    with _lock:
        if _histogram is None:
            meter: Meter = metrics.get_meter(_INSTRUMENTATION_SCOPE)
            _histogram = meter.create_histogram(
                name=_HISTOGRAM_NAME,
                unit=_HISTOGRAM_UNIT,
                description=_HISTOGRAM_DESCRIPTION,
            )
        return _histogram


def record_token_usage(
    token_type: str,
    count: int,
    *,
    model: Optional[str] = None,
    operation_name: str = OPERATION_NAME_CHAT,
    thread_id: Optional[str] = None,
    extra_attributes: Optional[Mapping[str, str]] = None,
) -> None:
    """Record a token-usage histogram observation.

    Parameters
    ----------
    token_type:
        One of :data:`TOKEN_TYPE_INPUT`, :data:`TOKEN_TYPE_OUTPUT`,
        :data:`TOKEN_TYPE_CACHE_READ`, :data:`TOKEN_TYPE_REASONING`.
        Free-form values are accepted (forwarded as-is) but discouraged.
    count:
        Number of tokens. Non-positive counts are dropped so dashboards
        do not see zero-noise on missing fields.
    model:
        ``gen_ai.request.model`` (e.g. ``gemini-2.5-flash``). Optional but
        strongly recommended.
    operation_name:
        ``gen_ai.operation.name`` (defaults to ``chat``).
    thread_id:
        Conversation thread id. Caller is responsible for any sanitisation
        the threat model requires (do not pass raw E.164 numbers).
    extra_attributes:
        Additional dimensions to attach. Caller-provided keys override the
        ones built from the named parameters.

    The function never raises. If the OTel SDK is not configured we record
    against a no-op histogram (transparent).
    """
    if not isinstance(count, int):
        try:
            count = int(count)
        except (TypeError, ValueError):
            return
    if count <= 0:
        return

    attributes: dict[str, str] = {ATTR_TOKEN_TYPE: str(token_type)}
    if model:
        attributes[ATTR_REQUEST_MODEL] = str(model)
    if operation_name:
        attributes[ATTR_OPERATION_NAME] = str(operation_name)
    if thread_id:
        attributes[ATTR_THREAD_ID] = str(thread_id)
    if extra_attributes:
        for key, value in extra_attributes.items():
            attributes[str(key)] = str(value)

    histogram = _get_histogram()
    histogram.record(count, attributes=attributes)


def reset_token_metrics_for_testing() -> None:
    """Drop the cached histogram so tests can install a fresh MeterProvider.

    Calling this in production is a footgun (the next ``record_token_usage``
    will resolve a new histogram against whatever the current global meter
    provider is). Test fixtures call it under controlled conditions.
    """
    global _histogram
    with _lock:
        _histogram = None
