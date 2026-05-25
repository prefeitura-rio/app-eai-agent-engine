"""Engine uncertainty quantification (Iter 3 do plano-bot-2026-loop-v2).

Submodules:
- calibration: pure ECE + reliability bins + temperature scaling (Guo et al. 2017).

This is the decision-independent calibration CORE — pure math, no bot wiring,
no I/O. It is the foundation for Iter 3 Phase B; the confidence-signal
composition, refusal threshold, and agent integration are deferred to the
full Phase B (behind the A→B sign-off). Computing a *real* ECE against the
bot requires the human-annotated golden dataset (task #208) — this module
only provides the mechanics, validated by unit tests on synthetic fixtures.
"""

from engine.uncertainty.calibration import (
    ReliabilityBin,
    TemperatureScaler,
    expected_calibration_error,
    reliability_bins,
)

__all__ = [
    "ReliabilityBin",
    "TemperatureScaler",
    "expected_calibration_error",
    "reliability_bins",
]
