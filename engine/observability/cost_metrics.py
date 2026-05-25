"""Emit per-request USD cost as an OTel metric (Iter 4 Phase B Tier 1).

Computes cost via the pure ``cost`` module and records it on the histogram
``gen_ai.client.cost.usd``, alongside the token histogram, so the existing
OTLP sink (Grafana/Mimir) gets cost as a first-class, queryable dimension —
no separate aggregation pipeline and no BigQuery decision required.

Why emit cost here (vs aggregate at query time)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The cost formula has subtle rules (input ⊇ cache_read; reasoning is additive
to output, both output-priced) — reimplementing it in PromQL/SQL would risk
the double-count / dropped-thinking bugs ``cost.py`` exists to prevent.
Computing in-Engine reuses
that single tested implementation. Trade-off: the rate card is baked into
the running image, so a price change needs a redeploy (acceptable for a POC
cost dashboard; documented in ADR-034).

Scope (Tier 1, text-only — declared)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Until the telemetry carries a modality dimension, every request is priced as
TEXT. Audio input is thereby under-priced (text $0.30 vs audio $1.00 per 1M).
The metric carries ``cost.scope="text-only"`` so dashboards know this, and
cache-storage cost is NOT attributed here (it needs TTL tracking — separate
concern). Both are explicit scope-outs, not silent gaps.

Resilience
~~~~~~~~~~
Cost is observability — it must NEVER break a citizen turn. Unknown model,
unknown modality, or token-subset violations are caught, logged, and skipped
(no emission) rather than raised. Mirrors ``token_metrics`` discipline.

Side-effect-free at import: the meter is resolved lazily on first record, so
import order does not constrain when OTel is configured.
"""

from __future__ import annotations

import threading
from typing import Final, Optional

from opentelemetry import metrics
from opentelemetry.metrics import Histogram, Meter

from engine.log import logger
from engine.observability.cost import (
    Modality,
    TokenSubsetError,
    TokenUsage,
    UnknownModalityError,
    UnknownModelError,
    compute_cost_usd,
)
from engine.observability.token_metrics import (
    ATTR_OPERATION_NAME,
    ATTR_REQUEST_MODEL,
    ATTR_THREAD_ID,
    OPERATION_NAME_CHAT,
)

ATTR_COST_SCOPE: Final[str] = "cost.scope"
SCOPE_TEXT_ONLY: Final[str] = "text-only"

_HISTOGRAM_NAME: Final[str] = "gen_ai.client.cost.usd"
_HISTOGRAM_UNIT: Final[str] = "USD"
_HISTOGRAM_DESCRIPTION: Final[str] = (
    "Estimated USD cost per GenAI request, computed from token usage via the "
    "verified rate card. Dimensions: gen_ai.request.model, gen_ai.operation.name, "
    "thread.id, cost.scope (text-only until modality is instrumented)."
)
_INSTRUMENTATION_SCOPE: Final[str] = "engine.observability.cost_metrics"

_lock = threading.Lock()
_histogram: Optional[Histogram] = None


def _get_histogram() -> Histogram:
    """Resolve the cost histogram lazily (same pattern as token_metrics)."""

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


def record_cost_usd(
    usage: TokenUsage,
    model: str,
    *,
    modality: Modality = Modality.TEXT,
    operation_name: str = OPERATION_NAME_CHAT,
    thread_id: Optional[str] = None,
) -> Optional[float]:
    """Compute and record the USD cost of ``usage``.

    Returns the recorded cost on success, or ``None`` if cost could not be
    computed (unknown model/modality or token-subset violation) — in which
    case a warning is logged and nothing is emitted. Never raises: cost is
    observability and must not break the turn.

    Scope: ``modality`` defaults to TEXT (Tier 1 text-only). The emitted
    metric carries ``cost.scope=text-only`` when modality is TEXT so the
    declared approximation is visible downstream.
    """

    # Coerce to the enum first: ``Modality`` is a str-enum, so a caller (or a
    # telemetry/config value) passing the plain string ``"text"`` would slip
    # through compute_cost_usd but then blow up on ``modality.value`` below,
    # breaking the never-raises contract. ``Modality(x)`` is idempotent for an
    # enum member and accepts valid strings; invalid values degrade to skip.
    try:
        modality = Modality(modality)
    except ValueError as exc:
        logger.warning(
            f"[Cost Metrics] Skipping cost emission — invalid modality "
            f"{modality!r} for model={model!r}: {exc}"
        )
        return None

    try:
        cost_usd = compute_cost_usd(usage, model, modality)
    except (UnknownModelError, UnknownModalityError, TokenSubsetError) as exc:
        logger.warning(
            f"[Cost Metrics] Skipping cost emission for model={model!r} "
            f"modality={modality.value}: {exc}"
        )
        return None

    attributes: dict[str, str] = {
        ATTR_REQUEST_MODEL: str(model),
        ATTR_COST_SCOPE: SCOPE_TEXT_ONLY if modality is Modality.TEXT else modality.value,
    }
    if operation_name:
        attributes[ATTR_OPERATION_NAME] = str(operation_name)
    if thread_id:
        attributes[ATTR_THREAD_ID] = str(thread_id)

    # Guard the OTel emission too, so this function honors its "never raises"
    # contract standalone (not only when the caller happens to wrap it). A
    # misconfigured MeterProvider must not break a citizen turn.
    try:
        _get_histogram().record(cost_usd, attributes=attributes)
    except Exception as exc:  # noqa: BLE001 — observability must not break turn
        logger.warning(
            f"[Cost Metrics] Failed to emit cost histogram for model={model!r}: {exc}"
        )
        return None
    return cost_usd


def reset_cost_metrics_for_testing() -> None:
    """Drop the cached histogram so tests can install a fresh MeterProvider."""

    global _histogram
    with _lock:
        _histogram = None
