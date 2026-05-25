"""Judge-infra Tier 0: shared LLM-as-judge (ADR-038).

The faithfulness + policy + tool-misuse judges that Iter 2 (sampler input),
Iter 3 (confidence signal), and Iter 5 (judge-of-judges) all assume but that
was never built. Each judge is an independent LLM call with structured output;
the orchestrator emits the ``{faithfulness, policy, tool_misuse} -> verdict``
panel that ``engine.adversarial.adjudication.PromptOutcome`` consumes, and a
per-judge ``confidence`` that ``engine.uncertainty.calibration`` can score.

Scope: in development/pre-production, synthetic self-generated cases are valid
for building and selecting the approach. The anti-tautological rule (≥50 human
annotations, ≥0.85 judge accuracy) is a PRODUCTION gate, not a dev blocker;
results over synthetic data are dev-only, never production metrics.
"""
