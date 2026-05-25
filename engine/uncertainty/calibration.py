"""Calibration mechanics for uncertainty quantification (Iter 3, pure core).

Implements the standard tools from Guo et al. 2017 ("On Calibration of Modern
Neural Networks", arXiv:1706.04599):

- ``expected_calibration_error`` (ECE) — the Iter 3 primary metric.
- ``reliability_bins`` — per-bin (confidence, accuracy, count) for reliability
  diagrams.
- ``TemperatureScaler`` — single-parameter post-hoc recalibration for binary
  confidences.

Scope (decision-independent, behavior-neutral)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This is PURE math on ``(confidence, correctness)`` arrays. It does NOT:
- read logprobs / call the LLM,
- compose the 3 confidence signals (avgLogprobs + self-consistency +
  faithfulness) — that needs calibration data + weights (Iter 3 Phase B),
- decide a refusal threshold or touch the agent — deferred to Phase B wiring.

A *real* ECE measured against the bot needs the human-annotated golden set
(task #208). This module is validated only by unit tests on synthetic
fixtures (mechanics correctness, NOT hypothesis validation): e.g. a perfectly
calibrated synthetic set has ECE≈0, an overconfident one has ECE>0, and
temperature scaling reduces the overconfident set's ECE.

Conventions
~~~~~~~~~~~
- ``confidences``: model's predicted probability of being correct, in [0, 1].
- ``correctness``: 1 if the answer was correct, 0 otherwise (binary).
- Binary calibration (correct vs not) matches the Iter 3 framing: "when the
  bot says it's X% sure, is it right ~X% of the time?".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

DEFAULT_N_BINS: Final[int] = 10
# Newton/line-search bounds for the temperature parameter. T>1 softens
# (fixes overconfidence), T<1 sharpens. Kept positive and bounded so the
# optimiser cannot wander into degenerate regions.
_MIN_TEMPERATURE: Final[float] = 1e-2
_MAX_TEMPERATURE: Final[float] = 1e2
_EPS: Final[float] = 1e-12


@dataclass(frozen=True)
class ReliabilityBin:
    """One confidence bin of a reliability diagram.

    Attributes:
        lower: inclusive lower edge of the confidence bin.
        upper: exclusive upper edge (inclusive for the last bin).
        count: number of samples that fell in the bin.
        mean_confidence: mean predicted confidence of samples in the bin.
        accuracy: fraction of correct samples in the bin.
    """

    lower: float
    upper: float
    count: int
    mean_confidence: float
    accuracy: float


def _check_confidence_values(confidences: np.ndarray) -> None:
    """Validate that confidences are finite and in [0, 1].

    The finite check MUST precede the range check: ``NaN < 0`` and
    ``NaN > 1`` are both ``False``, so a NaN would slip past the range
    check and silently produce NaN logits / NaN ECE downstream.
    """

    if not np.all(np.isfinite(confidences)):
        raise ValueError("confidences must be finite (no NaN/inf)")
    if np.any((confidences < 0.0) | (confidences > 1.0)):
        raise ValueError("confidences must be in [0, 1]")


def _validate(confidences: np.ndarray, correctness: np.ndarray) -> None:
    if confidences.shape != correctness.shape:
        raise ValueError(
            f"confidences {confidences.shape} and correctness "
            f"{correctness.shape} must have the same shape"
        )
    if confidences.ndim != 1:
        raise ValueError("confidences/correctness must be 1-D")
    if confidences.size == 0:
        raise ValueError("confidences/correctness must be non-empty")
    _check_confidence_values(confidences)
    if not np.all(np.isin(correctness, (0, 1))):
        raise ValueError("correctness must be binary (0 or 1)")


def reliability_bins(
    confidences: np.ndarray,
    correctness: np.ndarray,
    n_bins: int = DEFAULT_N_BINS,
) -> list[ReliabilityBin]:
    """Partition [0,1] into ``n_bins`` equal-width bins and summarise each.

    Empty bins are included with ``count=0`` so the diagram has a stable
    x-axis. Bin edges are equal-width (Guo et al. use equal-width bins for
    ECE).
    """

    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    confidences = np.asarray(confidences, dtype=np.float64)
    correctness = np.asarray(correctness, dtype=np.float64)
    _validate(confidences, correctness)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[ReliabilityBin] = []
    for index in range(n_bins):
        lower, upper = edges[index], edges[index + 1]
        # Last bin includes the right edge so confidence==1.0 lands somewhere.
        if index == n_bins - 1:
            mask = (confidences >= lower) & (confidences <= upper)
        else:
            mask = (confidences >= lower) & (confidences < upper)
        count = int(mask.sum())
        if count == 0:
            bins.append(ReliabilityBin(lower, upper, 0, 0.0, 0.0))
            continue
        bins.append(
            ReliabilityBin(
                lower=float(lower),
                upper=float(upper),
                count=count,
                mean_confidence=float(confidences[mask].mean()),
                accuracy=float(correctness[mask].mean()),
            )
        )
    return bins


def expected_calibration_error(
    confidences: np.ndarray,
    correctness: np.ndarray,
    n_bins: int = DEFAULT_N_BINS,
) -> float:
    """Expected Calibration Error (Guo et al. 2017).

    ECE = Σ_b (|b| / N) · |acc(b) − conf(b)|, over equal-width bins ``b``.
    0 means perfectly calibrated; higher is worse. Range [0, 1].
    """

    confidences = np.asarray(confidences, dtype=np.float64)
    correctness = np.asarray(correctness, dtype=np.float64)
    _validate(confidences, correctness)
    total = confidences.size
    ece = 0.0
    for current_bin in reliability_bins(confidences, correctness, n_bins):
        if current_bin.count == 0:
            continue
        weight = current_bin.count / total
        ece += weight * abs(current_bin.accuracy - current_bin.mean_confidence)
    return ece


def _to_logit(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, _EPS, 1.0 - _EPS)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    # Clip before exp: confidence 0.0/1.0 (allowed by validation) → logit ≈
    # ∓27.6, and a small temperature divides that to ≈∓2763, overflowing
    # np.exp and emitting RuntimeWarnings (or failing under seterr(over=
    # 'raise')). sigmoid(±700) is already 0/1 to float64 precision, so
    # clipping to ±700 is numerically lossless and overflow-safe.
    return 1.0 / (1.0 + np.exp(-np.clip(values, -700.0, 700.0)))


class TemperatureScaler:
    """Single-parameter temperature scaling for binary confidences.

    Calibrated probability = ``sigmoid(logit(p) / T)``. ``T > 1`` softens
    overconfident probabilities toward 0.5; ``T < 1`` sharpens. The optimal
    ``T`` minimises negative log-likelihood on a held-out calibration set —
    post-hoc, preserving the ranking/accuracy (Guo et al. 2017).

    Usage::

        scaler = TemperatureScaler().fit(cal_conf, cal_labels)
        calibrated = scaler.transform(test_conf)
    """

    def __init__(self) -> None:
        self._temperature: float | None = None

    @property
    def temperature(self) -> float:
        if self._temperature is None:
            raise RuntimeError("TemperatureScaler must be fit() before use")
        return self._temperature

    def fit(
        self,
        confidences: np.ndarray,
        correctness: np.ndarray,
        n_grid: int = 100,
    ) -> "TemperatureScaler":
        """Fit the temperature by minimising NLL over a log-spaced grid.

        A 1-D grid search is robust and dependency-free (no scipy) and is
        more than adequate for a single scalar on a low-data regime (the
        Iter 3 golden set is ~200 examples).
        """

        confidences = np.asarray(confidences, dtype=np.float64)
        correctness = np.asarray(correctness, dtype=np.float64)
        _validate(confidences, correctness)
        if n_grid < 2:
            raise ValueError("n_grid must be ≥ 2")

        logits = _to_logit(confidences)
        # Include T=1.0 (identity) explicitly so a well-calibrated set can fit
        # exactly to "no change" rather than the nearest off-grid point.
        grid = np.unique(
            np.append(np.geomspace(_MIN_TEMPERATURE, _MAX_TEMPERATURE, n_grid), 1.0)
        )
        nlls = np.empty(grid.shape, dtype=np.float64)
        for index, temperature in enumerate(grid):
            calibrated = np.clip(_sigmoid(logits / temperature), _EPS, 1.0 - _EPS)
            nlls[index] = -np.mean(
                correctness * np.log(calibrated)
                + (1.0 - correctness) * np.log(1.0 - calibrated)
            )
        # Break ties TOWARD identity (T=1.0): a flat / no-signal set (e.g. all
        # confidences 0.5) gives identical NLL for every T, so "first strict
        # improvement" would lock T to the grid's smallest value (extreme
        # sharpening → severe overconfidence). Among all temperatures within a
        # numerical tie of the minimum NLL, pick the one closest to 1.0.
        tie_mask = nlls <= nlls.min() + 1e-9
        candidates = grid[tie_mask]
        self._temperature = float(candidates[np.argmin(np.abs(candidates - 1.0))])
        return self

    def transform(self, confidences: np.ndarray) -> np.ndarray:
        """Apply the fitted temperature to new confidences → calibrated probs."""

        confidences = np.asarray(confidences, dtype=np.float64)
        _check_confidence_values(confidences)
        return _sigmoid(_to_logit(confidences) / self.temperature)
