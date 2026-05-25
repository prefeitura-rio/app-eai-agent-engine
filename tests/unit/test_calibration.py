"""Unit tests for ``engine.uncertainty.calibration``.

These validate MECHANICS correctness on synthetic fixtures — NOT the Iter 3
hypothesis (a real ECE against the bot needs the human golden set, #208).

Coverage:
- ECE ≈ 0 for a perfectly-calibrated synthetic set.
- ECE > 0 for an overconfident set, and quantified vs a hand-computed value.
- reliability_bins: edges, empty bins, accuracy/confidence per bin.
- TemperatureScaler reduces ECE on an overconfident set (T > 1).
- Temperature scaling preserves ranking (monotonic) — accuracy unchanged.
- Validation: shape mismatch, out-of-range confidence, non-binary labels.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.uncertainty.calibration import (
    TemperatureScaler,
    expected_calibration_error,
    reliability_bins,
)


def _perfectly_calibrated(n_per_level: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """For each confidence level p in {0.1,...,0.9}, make exactly p fraction
    correct. A perfectly calibrated set → ECE ≈ 0."""

    rng = np.random.default_rng(42)
    confs: list[float] = []
    labels: list[int] = []
    for level in np.linspace(0.1, 0.9, 9):
        confs.extend([float(level)] * n_per_level)
        n_correct = int(round(level * n_per_level))
        bucket = [1] * n_correct + [0] * (n_per_level - n_correct)
        rng.shuffle(bucket)
        labels.extend(bucket)
    return np.array(confs), np.array(labels)


def test_ece_near_zero_for_perfect_calibration():
    confs, labels = _perfectly_calibrated()
    ece = expected_calibration_error(confs, labels, n_bins=10)
    assert ece < 0.01  # near-zero by construction (n_correct is exact here)


def test_ece_positive_for_overconfident():
    # Says 0.99 sure but only 50% correct → large miscalibration.
    confs = np.full(1000, 0.99)
    labels = np.array([1, 0] * 500)
    ece = expected_calibration_error(confs, labels, n_bins=10)
    # |acc(0.5) - conf(0.99)| ≈ 0.49, single populated bin → ECE ≈ 0.49
    assert ece == pytest.approx(0.49, abs=0.01)


def test_ece_zero_when_confidence_matches_accuracy_single_bin():
    # All conf 0.7, exactly 70% correct → ECE = 0.
    confs = np.full(100, 0.7)
    labels = np.array([1] * 70 + [0] * 30)
    assert expected_calibration_error(confs, labels, n_bins=10) == pytest.approx(0.0)


def test_reliability_bins_structure():
    confs = np.array([0.05, 0.15, 0.95])
    labels = np.array([0, 1, 1])
    bins = reliability_bins(confs, labels, n_bins=10)
    assert len(bins) == 10
    assert bins[0].count == 1 and bins[0].lower == pytest.approx(0.0)
    assert bins[1].count == 1
    assert bins[-1].count == 1 and bins[-1].upper == pytest.approx(1.0)
    # An untouched middle bin is present with count 0.
    assert bins[5].count == 0


def test_reliability_last_bin_includes_one():
    confs = np.array([1.0, 1.0])
    labels = np.array([1, 0])
    bins = reliability_bins(confs, labels, n_bins=10)
    assert bins[-1].count == 2
    assert bins[-1].accuracy == pytest.approx(0.5)
    assert bins[-1].mean_confidence == pytest.approx(1.0)


def test_temperature_scaling_reduces_ece_on_overconfident():
    """The load-bearing mechanics check: fitting temperature on an
    overconfident set lowers its ECE."""

    rng = np.random.default_rng(7)
    # Overconfident: true accuracy ~0.7 but model reports ~0.95.
    n = 2000
    labels = (rng.random(n) < 0.7).astype(int)
    confs = np.full(n, 0.95)
    ece_before = expected_calibration_error(confs, labels)

    scaler = TemperatureScaler().fit(confs, labels)
    calibrated = scaler.transform(confs)
    ece_after = expected_calibration_error(calibrated, labels)

    assert scaler.temperature > 1.0  # softening an overconfident set
    assert ece_after < ece_before
    assert ece_after < 0.1  # recalibrated toward the true 0.7


def test_temperature_scaling_preserves_ranking():
    """Temperature scaling is monotonic → it never reorders confidences,
    so it preserves accuracy/AUC (Guo et al.)."""

    scaler = TemperatureScaler()
    scaler._temperature = 2.5  # type: ignore[attr-defined]  # skip fit for a pure-monotonicity check
    raw = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    calibrated = scaler.transform(raw)
    assert np.all(np.diff(calibrated) > 0)  # strictly increasing preserved


def test_fit_no_signal_set_resolves_to_identity():
    """Flat/no-signal calibration set (all conf 0.5): every T gives the same
    NLL. Tie-break must pick T=1.0 (identity), NOT the grid's smallest T —
    otherwise later 0.2/0.8 would be sharpened to ~0/~1 (severe
    overconfidence from a no-signal set). Regression guard for the P2."""

    confs = np.full(500, 0.5)
    labels = np.array([1, 0] * 250)
    scaler = TemperatureScaler().fit(confs, labels)
    assert scaler.temperature == pytest.approx(1.0)
    # And transform must NOT sharpen unrelated confidences toward 0/1.
    out = scaler.transform(np.array([0.2, 0.8]))
    assert out == pytest.approx([0.2, 0.8])


def test_transform_before_fit_raises():
    with pytest.raises(RuntimeError, match="fit"):
        TemperatureScaler().transform(np.array([0.5]))


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_transform_rejects_non_finite(bad):
    scaler = TemperatureScaler()
    scaler._temperature = 1.5  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="finite"):
        scaler.transform(np.array([bad, 0.5]))


def test_transform_rejects_out_of_range():
    scaler = TemperatureScaler()
    scaler._temperature = 1.5  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        scaler.transform(np.array([1.5, 0.5]))


@pytest.mark.parametrize(
    "confs, labels, match",
    [
        (np.array([0.5, 0.5]), np.array([1]), "same shape"),
        (np.array([[0.5]]), np.array([[1]]), "1-D"),
        (np.array([]), np.array([]), "non-empty"),
        (np.array([1.5]), np.array([1]), r"\[0, 1\]"),
        (np.array([0.5]), np.array([2]), "binary"),
        (np.array([np.nan, 0.5]), np.array([1, 0]), "finite"),
        (np.array([np.inf, 0.5]), np.array([1, 0]), "finite"),
    ],
)
def test_validation_errors(confs, labels, match):
    with pytest.raises(ValueError, match=match):
        expected_calibration_error(confs, labels)


def test_fit_with_extreme_confidences_no_overflow():
    """Confidences of exactly 0.0/1.0 are valid; at small grid temperatures
    the scaled logit is huge. The stable sigmoid must not overflow — assert
    fit() works even under seterr(over='raise')."""

    confs = np.array([0.0, 1.0, 0.0, 1.0, 0.5, 0.5])
    labels = np.array([0, 1, 1, 1, 0, 1])
    with np.errstate(over="raise", invalid="raise"):
        scaler = TemperatureScaler().fit(confs, labels)
        out = scaler.transform(np.array([0.0, 1.0]))
    assert np.all(np.isfinite(out))
    assert 0.0 <= out[0] <= 1.0 and 0.0 <= out[1] <= 1.0


def test_temperature_one_is_identity():
    scaler = TemperatureScaler()
    scaler._temperature = 1.0  # type: ignore[attr-defined]
    raw = np.array([0.2, 0.6, 0.8])
    # sigmoid(logit(p)/1) == p
    assert np.allclose(scaler.transform(raw), raw)
