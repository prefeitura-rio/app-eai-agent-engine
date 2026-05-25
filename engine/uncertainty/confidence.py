"""Confidence composition + refusal threshold (Iter 3 Phase B, ADR-033).

The decision-independent core of Iter 3's confidence pipeline. ADR-033 decided
the bot's confidence must compose THREE complementary signals (logprobs alone
are unreliable), then be calibrated and gated by a refusal threshold:

    (a) avgLogprobs        — token-level model confidence (ChatVertexAI)
    (b) self-consistency   — agreement across N=3 sampled answers
    (c) faithfulness judge  — grounding of the answer in the evidence (RAGAS)

This module owns the parts that are PURE math given the signal values:

- ``compose_confidence`` — weighted average over the present signals (missing
  signals drop out and the remaining weights re-normalise), yielding a raw
  confidence in [0, 1].
- ``faithfulness_signal`` — maps a faithfulness-judge verdict (the judge-infra
  of ADR-038) to a [0, 1] signal: "judge says faithful, high confidence" → high.
- ``grid_search_threshold`` — picks the refusal threshold τ that minimises the
  false-confident rate (answered-but-wrong) subject to a cap on the refusal
  rate, exactly the trade-off ADR-033's hypothesis targets.
- ``should_refuse`` — below τ the bot refuses + hands off, rather than inventing.

It does NOT produce the signals (logprobs / self-consistency sampling need the
live LLM; the faithfulness verdict comes from ``engine.judges``) and it does
NOT calibrate — calibration is ``engine.uncertainty.calibration.TemperatureScaler``
(already built). Real thresholds/weights need the annotated golden dataset; in
dev, synthetic fixtures exercise the mechanics (ADR-038 dev-vs-prod rule).

Fail-fast: a signal outside [0, 1], an empty signal set, or non-positive total
weight is a data-integrity error and is raised — never silently coerced, the
same stance as ``calibration`` / ``cost`` / ``adjudication``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import numpy as np

SignalName = str
DEFAULT_WEIGHTS: Final[Mapping[SignalName, float]] = {
    "faithfulness": 1.0,
    "self_consistency": 1.0,
    "logprob": 1.0,
}
DEFAULT_MAX_REFUSAL_RATE: Final[float] = 0.10
DEFAULT_THRESHOLD_GRID_STEPS: Final[int] = 101


class ConfidenceError(Exception):
    """Signal/weight data that cannot be fairly composed."""


@dataclass(frozen=True)
class ConfidenceSignals:
    """The three confidence signals for one answer; any may be ``None`` (not
    available for this turn). Each present value must be in [0, 1]."""

    faithfulness: float | None = None
    self_consistency: float | None = None
    logprob: float | None = None

    def present(self) -> dict[SignalName, float]:
        """The signals that are available, by name."""
        return {
            name: value
            for name, value in (
                ("faithfulness", self.faithfulness),
                ("self_consistency", self.self_consistency),
                ("logprob", self.logprob),
            )
            if value is not None
        }


def _check_unit_interval(value: float, label: str) -> None:
    if not np.isfinite(value):
        raise ConfidenceError(f"{label} must be finite, got {value!r}")
    if not 0.0 <= value <= 1.0:
        raise ConfidenceError(f"{label} must be in [0, 1], got {value!r}")


def faithfulness_signal(verdict_is_failure: bool, judge_confidence: float) -> float:
    """Map a faithfulness-judge verdict to a [0, 1] faithfulness signal.

    The judge reports ``verdict_is_failure`` (True = NON-faithful / hallucinated)
    plus its confidence IN that verdict. The signal is high when the answer is
    faithful, low when not, and 0.5 (maximum uncertainty) when the judge is not
    committed.

    Only confidence ABOVE 0.5 carries usable signal: ``strength = max(0, conf -
    0.5) * 2`` ∈ [0, 1] is applied toward faithful (verdict ok) or non-faithful
    (failure). A verdict the judge holds with ≤0.5 confidence yields 0.5 — it
    stays uncertain rather than flipping the composer toward the opposite
    conclusion (a weakly-held "non-faithful" must NOT read as "confidently
    faithful"). So conf 0.9 → 0.9/0.1, conf ≤0.5 → 0.5, monotonic between.
    """
    _check_unit_interval(judge_confidence, "judge_confidence")
    strength = max(0.0, judge_confidence - 0.5) * 2.0  # [0, 1] for conf in [0.5, 1]
    return (0.5 - strength / 2.0) if verdict_is_failure else (0.5 + strength / 2.0)


def compose_confidence(
    signals: ConfidenceSignals, weights: Mapping[SignalName, float] = DEFAULT_WEIGHTS
) -> float:
    """Weighted average of the PRESENT signals (missing signals drop out and the
    remaining weights re-normalise). Returns a raw confidence in [0, 1]."""
    present = signals.present()
    if not present:
        raise ConfidenceError("at least one confidence signal must be present")

    total_weight = 0.0
    weighted_sum = 0.0
    for name, value in present.items():
        _check_unit_interval(value, f"signal {name!r}")
        weight = weights.get(name, 0.0)
        if weight < 0.0 or not np.isfinite(weight):
            raise ConfidenceError(f"weight for {name!r} must be finite and ≥ 0, got {weight!r}")
        total_weight += weight
        weighted_sum += weight * value

    if total_weight <= 0.0:
        raise ConfidenceError("total weight over present signals must be > 0")
    return weighted_sum / total_weight


def should_refuse(confidence: float, threshold: float) -> bool:
    """The bot refuses (and hands off to a human) when confidence is strictly
    below the calibrated threshold."""
    _check_unit_interval(confidence, "confidence")
    _check_unit_interval(threshold, "threshold")
    return confidence < threshold


def grid_search_threshold(
    confidences: np.ndarray,
    correctness: np.ndarray,
    max_refusal_rate: float = DEFAULT_MAX_REFUSAL_RATE,
    grid_steps: int = DEFAULT_THRESHOLD_GRID_STEPS,
) -> float:
    """Pick the refusal threshold τ that minimises the false-confident rate
    (answered AND wrong, over all cases) subject to ``refusal_rate ≤
    max_refusal_rate``.

    Below τ the answer is refused; at/above τ it is answered. τ=0 (refuse
    nothing) is always feasible, so a threshold always exists. Ties break toward
    the SMALLEST τ — refuse as little as possible for the same false-confident
    rate, honouring ADR-033's "don't inflate the generic refusal rate".

    Precondition — pass CALIBRATED confidences (the ADR-033 pipeline is
    compose → ``TemperatureScaler.transform`` → here). The scaler's sigmoid maps
    into the open interval (0, 1), so a confidently-wrong answer is pulled below
    1.0 and becomes refusable. A *raw*, uncalibrated confidence of exactly 1.0
    cannot be refused by a threshold in [0, 1] under refuse-if-`< τ` semantics
    (it would need τ > 1.0); calibration — not the threshold — is the mechanism
    for over-confident answers, so τ minimises false-confident over the
    refusable region (confidence < 1.0).

    Args:
        confidences: calibrated confidences in [0, 1], shape (n,).
        correctness: 1/True where the answer was correct, shape (n,).
        max_refusal_rate: cap on the fraction of cases refused.
        grid_steps: number of candidate thresholds in [0, 1] inclusive.
    """
    confidences = np.asarray(confidences, dtype=float)
    correctness = np.asarray(correctness, dtype=float)
    if confidences.shape != correctness.shape:
        raise ConfidenceError(
            f"confidences {confidences.shape} and correctness {correctness.shape} must match"
        )
    if confidences.ndim != 1 or confidences.size == 0:
        raise ConfidenceError("confidences/correctness must be non-empty 1-D arrays")
    if np.any(~np.isfinite(confidences)) or np.any((confidences < 0.0) | (confidences > 1.0)):
        raise ConfidenceError("confidences must be finite and in [0, 1]")
    if np.any(~np.isin(correctness, (0.0, 1.0))):  # binary, like calibration._validate
        raise ConfidenceError("correctness must be binary (0/1 or bool)")
    correctness = correctness.astype(bool)
    if not 0.0 <= max_refusal_rate <= 1.0:
        raise ConfidenceError("max_refusal_rate must be in [0, 1]")
    if grid_steps < 2:
        raise ConfidenceError("grid_steps must be ≥ 2")

    total = confidences.size
    best_threshold = 0.0
    best_false_confident = np.inf
    for threshold in np.linspace(0.0, 1.0, grid_steps):
        answered = confidences >= threshold
        refusal_rate = float(np.mean(~answered))
        if refusal_rate > max_refusal_rate:
            continue
        false_confident_rate = float(np.sum(answered & ~correctness)) / total
        if false_confident_rate < best_false_confident:
            best_false_confident = false_confident_rate
            best_threshold = float(threshold)
    return best_threshold
