"""Few-shot example injection for Active Learning treatment variant.

Scope
~~~~~
Builds the ``SystemMessage`` that carries retrieved few-shot demonstrations
into the LLM call when the experiment flag resolves to ``treatment``.
The actual wiring into ``Agent._combined_pre_model_hook`` is deferred to
a follow-up commit so the hook can be A/B-tested before it ships behind
a runtime flag — this module is intentionally *callable from anywhere*
and free of LangGraph state-machinery assumptions.

Contract
~~~~~~~~
- Input: an ordered list of ``FewShotExample`` (citizen turn, bot turn).
- Output: a single ``SystemMessage`` rendered with a stable template, or
  ``None`` if the input is empty (so the caller can skip injection cheaply).
- The renderer is **deterministic**: same input → byte-identical output.
  That property matters for prompt-cache hit rates (Gemini Flash cached
  content key is the prefix bytes).

Why not append to existing system_prompt?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The Agent caches its system_prompt via Gemini explicit cache (see
``engine/caching/gemini_cache.py``). Mutating ``self._system_prompt``
per-turn destroys the cache. Injecting a *separate* SystemMessage in the
pre-model hook keeps the cached prefix intact and only adds 1-3 turn-worth
of tokens for the demonstrations.

Limitations (deferred to Iter 3+):
- No token-budget enforcement. Caller must trim ``examples`` before
  calling (top-K=3 is the calibrated target from Iter 2 Phase A).
- No PII redaction of examples. Examples MUST come from annotated golden
  data that was redacted at annotation time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from langchain_core.messages import SystemMessage

PREAMBLE: Final[str] = (
    "Exemplos de respostas anteriores anotadas como corretas por servidores OPS. "
    "Use o padrão de tom, comprimento e estrutura desses exemplos quando relevante."
)
EXAMPLE_SEPARATOR: Final[str] = "\n\n---\n\n"
CITIZEN_PREFIX: Final[str] = "Cidadão:"
BOT_PREFIX: Final[str] = "Resposta correta:"


@dataclass(frozen=True)
class FewShotExample:
    """One annotated (citizen-turn, bot-turn) pair.

    Both sides are already PII-redacted (annotation pipeline runs PII
    redaction before persistence). The injector does not re-validate.

    Contract assumptions (annotation pipeline is responsible):
    - Neither turn is empty / whitespace-only.
    - Neither turn contains the literal sequence ``\\n\\n---\\n\\n`` (the
      example separator) — collisions would confuse any downstream parser
      that re-splits the block. Enforced here as fail-fast on construction.
    """

    citizen_turn: str
    bot_turn: str

    def __post_init__(self) -> None:
        if not self.citizen_turn or not self.citizen_turn.strip():
            raise ValueError("FewShotExample.citizen_turn must be non-empty")
        if not self.bot_turn or not self.bot_turn.strip():
            raise ValueError("FewShotExample.bot_turn must be non-empty")
        if EXAMPLE_SEPARATOR in self.citizen_turn:
            raise ValueError(
                "FewShotExample.citizen_turn must not contain the example separator"
            )
        if EXAMPLE_SEPARATOR in self.bot_turn:
            raise ValueError(
                "FewShotExample.bot_turn must not contain the example separator"
            )


def render_few_shot_block(examples: list[FewShotExample]) -> str:
    """Render examples into the deterministic prompt block.

    Returns an empty string if examples is empty, so callers can use
    ``if not block: return state`` to short-circuit.
    """

    if not examples:
        return ""

    rendered_examples = [
        f"{CITIZEN_PREFIX} {example.citizen_turn}\n{BOT_PREFIX} {example.bot_turn}"
        for example in examples
    ]
    body = EXAMPLE_SEPARATOR.join(rendered_examples)
    return f"{PREAMBLE}\n\n{body}"


def build_few_shot_message(examples: list[FewShotExample]) -> SystemMessage | None:
    """Build a SystemMessage carrying the examples, or None if empty.

    Caller is responsible for appending the message to state messages in
    the appropriate position (after the cached system prompt prefix,
    before the conversation history).
    """

    block = render_few_shot_block(examples)
    if not block:
        return None
    return SystemMessage(content=block)
