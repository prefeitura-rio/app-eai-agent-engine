"""Engine adversarial evaluation (Iter 5 do plano-bot-2026-loop-v2).

Submodules:
- adjudication: pure bypass-adjudication math (judge-of-judges aggregation,
  bypass rate, per-category breakdown, per-judge alignment, CI gate decision).

This is the decision-independent Tier 1 CORE — pure aggregation over judge
verdicts. It does NOT produce verdicts: the LLM judges (faithfulness +
policy + tool-misuse) are Tier 0, a shared prerequisite assumed by Iter 2/3/5
and not yet built (see ADR-035). A *real* bypass rate needs those judges,
calibrated ≥0.85 against ≥50 human annotations (#208-class blocker). This
module is validated only by unit tests on synthetic verdict fixtures.
"""

from engine.adversarial.adjudication import (
    PromptOutcome,
    RunReport,
    adjudicate_run,
    gate_passes,
    is_bypass_confirmed,
)

__all__ = [
    "PromptOutcome",
    "RunReport",
    "adjudicate_run",
    "gate_passes",
    "is_bypass_confirmed",
]
