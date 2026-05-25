"""Unit tests for ``engine.uncertainty.confidence`` (Iter 3 Phase B, ADR-033).

MECHANICS only on synthetic fixtures — pure composition / mapping / threshold
math. NOT accuracy validation (real weights + threshold need the annotated
golden dataset; production gate — ADR-033/ADR-038).

Coverage:
- compose_confidence: weighted average, missing-signal re-normalisation, single
  signal, custom weights; fail-fast (empty, out-of-range, bad weights).
- faithfulness_signal: faithful↔non-faithful mapping, max-uncertainty midpoint.
- should_refuse: strict-below threshold; fail-fast range.
- grid_search_threshold: refuses low-confidence wrong answers under the refusal
  cap, τ=0 feasibility, fail-fast on malformed arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.uncertainty.confidence import (
    ConfidenceError,
    ConfidenceSignals,
    compose_confidence,
    faithfulness_signal,
    grid_search_threshold,
    should_refuse,
)


# ---------- compose_confidence ----------


def test_compose_all_three_equal_weights():
    signals = ConfidenceSignals(faithfulness=0.9, self_consistency=0.6, logprob=0.3)
    assert compose_confidence(signals) == pytest.approx((0.9 + 0.6 + 0.3) / 3)


def test_compose_drops_missing_and_renormalises():
    # only two present → average of the two, NOT divided by 3.
    signals = ConfidenceSignals(faithfulness=0.9, logprob=0.5)
    assert compose_confidence(signals) == pytest.approx(0.7)


def test_compose_single_signal_returns_it():
    assert compose_confidence(ConfidenceSignals(self_consistency=0.42)) == pytest.approx(0.42)


def test_compose_custom_weights():
    signals = ConfidenceSignals(faithfulness=1.0, logprob=0.0)
    weights = {"faithfulness": 3.0, "logprob": 1.0}
    assert compose_confidence(signals, weights) == pytest.approx(0.75)


def test_compose_empty_raises():
    with pytest.raises(ConfidenceError, match="at least one"):
        compose_confidence(ConfidenceSignals())


@pytest.mark.parametrize("bad", [1.5, -0.1, float("nan")])
def test_compose_out_of_range_signal_raises(bad):
    with pytest.raises(ConfidenceError):
        compose_confidence(ConfidenceSignals(faithfulness=bad))


def test_compose_negative_weight_raises():
    with pytest.raises(ConfidenceError, match="≥ 0"):
        compose_confidence(ConfidenceSignals(faithfulness=0.5), {"faithfulness": -1.0})


def test_compose_zero_total_weight_raises():
    with pytest.raises(ConfidenceError, match="total weight"):
        compose_confidence(ConfidenceSignals(faithfulness=0.5), {"faithfulness": 0.0})


# ---------- faithfulness_signal ----------


def test_faithfulness_signal_confident_faithful_is_high():
    assert faithfulness_signal(verdict_is_failure=False, judge_confidence=0.9) == pytest.approx(0.9)


def test_faithfulness_signal_confident_unfaithful_is_low():
    assert faithfulness_signal(verdict_is_failure=True, judge_confidence=0.9) == pytest.approx(0.1)


def test_faithfulness_signal_low_confidence_is_midpoint():
    assert faithfulness_signal(True, 0.5) == pytest.approx(0.5)
    assert faithfulness_signal(False, 0.5) == pytest.approx(0.5)


def test_faithfulness_signal_below_half_stays_uncertain_not_flipped():
    # a weakly-held "non-faithful" verdict must NOT read as "confidently faithful"
    assert faithfulness_signal(True, 0.1) == pytest.approx(0.5)
    assert faithfulness_signal(False, 0.1) == pytest.approx(0.5)


def test_faithfulness_signal_monotonic_above_half():
    # stronger faithful verdict → higher signal; stronger failure → lower.
    assert faithfulness_signal(False, 0.7) == pytest.approx(0.7)
    assert faithfulness_signal(True, 0.7) == pytest.approx(0.3)


def test_faithfulness_signal_out_of_range_raises():
    with pytest.raises(ConfidenceError):
        faithfulness_signal(False, 1.2)


# ---------- should_refuse ----------


def test_should_refuse_strictly_below():
    assert should_refuse(0.49, 0.5) is True
    assert should_refuse(0.5, 0.5) is False
    assert should_refuse(0.51, 0.5) is False


def test_should_refuse_out_of_range_raises():
    with pytest.raises(ConfidenceError):
        should_refuse(1.1, 0.5)


# ---------- grid_search_threshold ----------


def test_grid_search_refuses_low_confidence_wrong_answer():
    # 0.2 is wrong; a good τ refuses it (answers 0.3-correct) under a 0.5 cap.
    confidences = np.array([0.9, 0.8, 0.3, 0.2])
    correctness = np.array([1, 0, 1, 0])
    tau = grid_search_threshold(confidences, correctness, max_refusal_rate=0.5)
    assert should_refuse(0.2, tau) is True
    assert should_refuse(0.3, tau) is False


def test_grid_search_tau_zero_when_no_refusal_allowed():
    confidences = np.array([0.9, 0.2])
    correctness = np.array([1, 0])
    # cap 0 forbids any refusal → τ must answer everything → τ = 0.
    assert grid_search_threshold(confidences, correctness, max_refusal_rate=0.0) == pytest.approx(0.0)


def test_grid_search_shape_mismatch_raises():
    with pytest.raises(ConfidenceError, match="must match"):
        grid_search_threshold(np.array([0.5, 0.6]), np.array([1]))


def test_grid_search_empty_raises():
    with pytest.raises(ConfidenceError, match="non-empty"):
        grid_search_threshold(np.array([]), np.array([]))


def test_grid_search_out_of_range_confidence_raises():
    with pytest.raises(ConfidenceError, match="in \\[0, 1\\]"):
        grid_search_threshold(np.array([1.5]), np.array([1]))


def test_grid_search_non_binary_correctness_raises():
    with pytest.raises(ConfidenceError, match="binary"):
        grid_search_threshold(np.array([0.9, 0.5]), np.array([2, 0]))


def test_grid_search_tie_break_picks_smallest_threshold():
    # all answers wrong → false-confident is minimised (0) by refusing all; the
    # smallest τ that refuses all (just above max conf) wins, not τ=1.0.
    confidences = np.array([0.1, 0.2, 0.3])
    correctness = np.array([0, 0, 0])
    tau = grid_search_threshold(confidences, correctness, max_refusal_rate=1.0)
    assert should_refuse(0.3, tau) is True  # refuses the highest (wrong) answer
    assert tau <= 0.4  # smallest-τ tie-break, did not jump to 1.0
