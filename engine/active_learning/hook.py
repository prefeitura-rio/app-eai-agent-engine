"""Pure orchestration helper for Active Learning few-shot injection.

Scope
~~~~~
Combines the three Phase B primitives (``flag_client``,
``fewshot_injector``, an external retriever) into a single pure function
suitable for calling from inside ``Agent._combined_pre_model_hook``.

The wiring into the live hook is intentionally deferred: the existing
hook is synchronous and ``FlagClient.assign`` is async. Resolving that
mismatch is out-of-scope for Phase B — see the *Sync/async bridge*
section below for the decision matrix. This module ships the pure logic
that the bridge will eventually call.

Sync/async bridge (Iter 3 follow-up)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The current ``_combined_pre_model_hook`` is sync. Three viable bridges:
1. Sync mirror of ``FlagClient`` using ``httpx.Client``. Cleanest, but
   duplicates the auth/header surface and risks drift.
2. Run-in-thread via ``asyncio.to_thread`` reversed; complicated by the
   hook running inside an already-async LangGraph runtime.
3. Pre-resolve assignment in the surrounding async caller (the
   query-handling layer), pass it down via ``config["configurable"]``.
   Decoupled and testable. Recommended.
The decision is intentionally not made here — this module accepts a
pre-resolved ``FlagAssignment`` so it stays sync-safe regardless.

Contract
~~~~~~~~
- Input: current state (messages list), the resolved ``FlagAssignment``
  or ``None``, and the retrieved ``FewShotExample`` list (may be empty).
- Output: new state with the few-shot ``SystemMessage`` injected after
  any existing leading SystemMessage(s) and before the conversation
  history. If variant != ``treatment`` or examples is empty, the state
  is returned unchanged.

The function is pure: it does not call the flag service or the
retriever. Callers must resolve both before invoking. This separation
lets the hook be unit-tested without network or model dependencies.
"""

from __future__ import annotations

from typing import Any, Final

from langchain_core.messages import BaseMessage, SystemMessage

from engine.active_learning.fewshot_injector import (
    FewShotExample,
    build_few_shot_message,
)
from engine.active_learning.flag_client import FlagAssignment

TREATMENT_VARIANT: Final[str] = "treatment"


def inject_few_shot_examples(
    state: dict[str, Any],
    assignment: FlagAssignment | None,
    examples: list[FewShotExample],
) -> dict[str, Any]:
    """Return new state with the few-shot SystemMessage injected.

    No-op (returns state unchanged, same dict reference) when:
    - ``assignment`` is ``None`` (flag service unavailable / not configured).
    - ``assignment.variant`` != ``treatment``.
    - ``examples`` is empty.

    The injected SystemMessage is positioned **after** any leading
    SystemMessage(s) — preserving the cached system prompt prefix — and
    before the first non-System message. Matches the existing
    long-term-memory injection ordering in ``Agent._inject_long_term_memory``.
    """

    if assignment is None or assignment.variant != TREATMENT_VARIANT:
        return state
    if not examples:
        return state

    few_shot_message = build_few_shot_message(examples)
    if few_shot_message is None:
        return state

    messages: list[BaseMessage] = list(state.get("messages", []))
    insert_index = _find_first_non_system_index(messages)
    messages.insert(insert_index, few_shot_message)

    new_state = dict(state)
    new_state["messages"] = messages
    return new_state


def _find_first_non_system_index(messages: list[BaseMessage]) -> int:
    """Return the index of the first non-SystemMessage, or len(messages)
    if every message is a SystemMessage (or the list is empty).
    """

    for index, message in enumerate(messages):
        if not isinstance(message, SystemMessage):
            return index
    return len(messages)
