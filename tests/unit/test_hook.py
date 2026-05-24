"""Unit tests for ``engine.active_learning.hook``.

Coverage targets:
- ``None`` assignment → state unchanged (same dict ref).
- ``control`` variant → state unchanged.
- ``treatment`` variant + empty examples → state unchanged.
- ``treatment`` + examples → new state with SystemMessage injected.
- Injection position: after leading SystemMessages, before first
  non-System message.
- Empty messages list → SystemMessage prepended at index 0.
- All-System messages → SystemMessage appended at end.
- Other state keys are preserved untouched.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from engine.active_learning.fewshot_injector import FewShotExample
from engine.active_learning.flag_client import FlagAssignment
from engine.active_learning.hook import inject_few_shot_examples


def _state_with(messages: list[BaseMessage], **extra) -> dict:
    return {"messages": messages, **extra}


def _example() -> FewShotExample:
    return FewShotExample(citizen_turn="q", bot_turn="a")


def _assignment(variant: str = "treatment") -> FlagAssignment:
    return FlagAssignment(flag="active_learning_v1", variant=variant, user_id="u-1")


def test_no_op_when_assignment_is_none():
    state = _state_with([HumanMessage(content="hi")])
    result = inject_few_shot_examples(state, assignment=None, examples=[_example()])
    assert result is state


def test_no_op_when_variant_is_control():
    state = _state_with([HumanMessage(content="hi")])
    result = inject_few_shot_examples(
        state, assignment=_assignment("control"), examples=[_example()]
    )
    assert result is state


def test_no_op_when_examples_empty():
    state = _state_with([HumanMessage(content="hi")])
    result = inject_few_shot_examples(state, assignment=_assignment(), examples=[])
    assert result is state


def test_treatment_with_examples_returns_new_state():
    original_messages = [HumanMessage(content="hi")]
    state = _state_with(list(original_messages))
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    assert result is not state
    assert result["messages"] is not state["messages"]
    assert len(result["messages"]) == 2


def test_inserts_after_leading_system_messages():
    system_msg = SystemMessage(content="cached system prompt")
    human_msg = HumanMessage(content="user input")
    state = _state_with([system_msg, human_msg])
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    assert isinstance(result["messages"][0], SystemMessage)
    assert result["messages"][0] is system_msg  # preserved
    assert isinstance(result["messages"][1], SystemMessage)  # injected few-shot
    assert result["messages"][1] is not system_msg
    assert result["messages"][2] is human_msg


def test_prepends_when_no_messages():
    state = _state_with([])
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], SystemMessage)


def test_appends_when_all_system_messages():
    system_msg = SystemMessage(content="cached")
    state = _state_with([system_msg, SystemMessage(content="memory")])
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    assert len(result["messages"]) == 3
    assert result["messages"][2].content != "cached"
    assert result["messages"][2].content != "memory"


def test_inserts_before_first_ai_message():
    state = _state_with(
        [
            SystemMessage(content="sys"),
            AIMessage(content="prior bot"),
            HumanMessage(content="follow-up"),
        ]
    )
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    # Injected at index 1 (right before the AIMessage).
    assert isinstance(result["messages"][1], SystemMessage)
    assert result["messages"][1].content.startswith("Exemplos")


def test_other_state_keys_preserved():
    state = _state_with([HumanMessage(content="hi")], extra_key="extra_value")
    result = inject_few_shot_examples(
        state, assignment=_assignment(), examples=[_example()]
    )
    assert result["extra_key"] == "extra_value"


def test_original_state_messages_not_mutated():
    original_messages = [HumanMessage(content="hi")]
    state = _state_with(original_messages)
    inject_few_shot_examples(state, assignment=_assignment(), examples=[_example()])
    # state["messages"] was a separate list; helper passed it directly,
    # so verify we did not mutate that list.
    assert len(original_messages) == 1
    assert original_messages == state["messages"]
