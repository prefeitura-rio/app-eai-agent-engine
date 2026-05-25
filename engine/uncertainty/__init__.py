"""Engine uncertainty quantification (Iter 3 do plano-bot-2026-loop-v2).

Submodules:
- calibration: pure ECE + reliability bins + temperature scaling (Guo et al. 2017).
- confidence: pure 3-signal composition + refusal-threshold grid search (ADR-033).

These are the decision-independent CORES — pure math, no bot wiring, no I/O.
The LLM-coupled signal producers (avgLogprobs, self-consistency sampling) and
the live agent integration remain deferred. Real weights/thresholds + a real
ECE against the bot need the annotated golden dataset; these modules provide
the mechanics, validated on synthetic fixtures (dev-vs-prod rule, ADR-038).
"""

from engine.uncertainty.calibration import (
    ReliabilityBin,
    TemperatureScaler,
    expected_calibration_error,
    reliability_bins,
)
from engine.uncertainty.confidence import (
    ConfidenceError,
    ConfidenceSignals,
    compose_confidence,
    faithfulness_signal,
    grid_search_threshold,
    should_refuse,
)

__all__ = [
    "ConfidenceError",
    "ConfidenceSignals",
    "ReliabilityBin",
    "TemperatureScaler",
    "compose_confidence",
    "expected_calibration_error",
    "faithfulness_signal",
    "grid_search_threshold",
    "reliability_bins",
    "should_refuse",
]
