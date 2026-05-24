"""Integration tests for Active Learning wiring inside ``engine.agent.Agent``.

These tests exercise the new ``_inject_active_learning_few_shot`` hook
directly, plus its participation in ``_combined_pre_model_hook``. They
cover the contract from Iter 2.5 sync/async bridge (Option 3):

1. Feature OFF by default — no config keys means state passes through unchanged.
2. Pre-resolved assignment + examples in ``config["configurable"]`` triggers injection.
3. Control variant is a no-op (no SystemMessage added).
4. Empty examples list is a no-op.
5. Missing config / non-dict config is safe.
6. Hook participates in the combined pre-model pipeline in the right order
   (after long-term memory injection, before short-term memory filtering).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from engine.active_learning import (
    FewShotExample,
    FlagAssignment,
)
from engine.agent import Agent


@pytest.fixture
def agent() -> Agent:
    """Minimal Agent — no Postgres / Vertex / MCP.

    The hook we exercise reads only ``config["configurable"]`` and the
    inject_few_shot_examples pure function.
    """

    return Agent(
        model="gemini-2.5-flash",
        system_prompt="(test prompt)",
        tools=[],
        otpl_service="test-engine",
    )


@pytest.fixture
def example() -> FewShotExample:
    return FewShotExample(citizen_turn="Cadê meu IPTU?", bot_turn="Você consulta em ...")


@pytest.fixture
def assignment_treatment() -> FlagAssignment:
    return FlagAssignment(
        flag="active_learning_v1",
        variant="treatment",
        user_id="user-1",
    )


@pytest.fixture
def assignment_control() -> FlagAssignment:
    return FlagAssignment(
        flag="active_learning_v1",
        variant="control",
        user_id="user-2",
    )


# ---------- _inject_active_learning_few_shot direct tests ----------


def test_no_config_returns_state_unchanged(agent: Agent, example: FewShotExample) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    result = agent._inject_active_learning_few_shot(state, config=None)
    assert result is state


def test_non_dict_config_returns_state_unchanged(
    agent: Agent, example: FewShotExample
) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    result = agent._inject_active_learning_few_shot(state, config="not-a-dict")
    assert result is state


def test_missing_assignment_key_returns_state_unchanged(agent: Agent) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {"configurable": {"thread_id": "t1"}}  # no AL keys
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is state


def test_treatment_with_examples_injects_system_message(
    agent: Agent,
    assignment_treatment: FlagAssignment,
    example: FewShotExample,
) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_treatment,
            "active_learning_examples": [example],
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is not state
    assert len(result["messages"]) == 2
    assert isinstance(result["messages"][0], SystemMessage)
    assert isinstance(result["messages"][1], HumanMessage)


def test_control_variant_is_noop(
    agent: Agent,
    assignment_control: FlagAssignment,
    example: FewShotExample,
) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_control,
            "active_learning_examples": [example],
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is state


def test_empty_examples_is_noop(
    agent: Agent, assignment_treatment: FlagAssignment
) -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_treatment,
            "active_learning_examples": [],
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is state


def test_missing_examples_key_defaults_to_empty_list(
    agent: Agent, assignment_treatment: FlagAssignment
) -> None:
    """When ``active_learning_examples`` is absent but assignment is treatment,
    we treat as empty list (no-op) rather than KeyError."""

    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_treatment,
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is state


def test_inserts_after_leading_system_messages(
    agent: Agent,
    assignment_treatment: FlagAssignment,
    example: FewShotExample,
) -> None:
    cached_prompt = SystemMessage(content="cached system prompt")
    user_msg = HumanMessage(content="hi")
    state: dict[str, Any] = {"messages": [cached_prompt, user_msg]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_treatment,
            "active_learning_examples": [example],
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    # cached prompt preserved at index 0; few-shot injected at index 1.
    assert result["messages"][0] is cached_prompt
    assert isinstance(result["messages"][1], SystemMessage)
    assert result["messages"][1] is not cached_prompt
    assert result["messages"][2] is user_msg


# ---------- Combined hook participation ----------


def test_combined_hook_threads_few_shot_through(
    agent: Agent,
    assignment_treatment: FlagAssignment,
    example: FewShotExample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies _combined_pre_model_hook calls _inject_active_learning_few_shot.

    Stubs the other steps so the test isolates AL injection's participation
    AND locks the call order between Steps 2, 2.5, 3, 4."""

    call_order: list[str] = []

    def _spy_timestamps(state):
        call_order.append("step_1_timestamps")
        return None

    def _spy_memory(state, config=None):
        call_order.append("step_2_memory")
        return state

    real_few_shot = agent._inject_active_learning_few_shot

    def _spy_few_shot(state, config=None):
        call_order.append("step_2_5_few_shot")
        return real_few_shot(state, config)

    def _spy_filter(state):
        call_order.append("step_3_filter")
        return {"messages": state["messages"]}

    def _spy_thread_id(state, config=None):
        call_order.append("step_4_thread_id")
        return state

    monkeypatch.setattr(agent, "_add_timestamp_to_tool_messages", _spy_timestamps)
    monkeypatch.setattr(agent, "_inject_long_term_memory", _spy_memory)
    monkeypatch.setattr(agent, "_inject_active_learning_few_shot", _spy_few_shot)
    monkeypatch.setattr(agent, "_filter_short_term_memory", _spy_filter)
    monkeypatch.setattr(agent, "_inject_thread_id_in_user_id_params", _spy_thread_id)

    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": assignment_treatment,
            "active_learning_examples": [example],
        }
    }
    result = agent._combined_pre_model_hook(state, config=config)
    messages = result.get("messages") or result.get("llm_input_messages") or []
    assert any(isinstance(m, SystemMessage) for m in messages)
    # Lock the call order — guards against future hook re-shuffles.
    assert call_order == [
        "step_1_timestamps",
        "step_2_memory",
        "step_2_5_few_shot",
        "step_3_filter",
        "step_4_thread_id",
    ]


def test_assignment_with_wrong_type_logs_warning_and_skips(
    agent: Agent,
    example: FewShotExample,
) -> None:
    """A misuse-case stale dict (vs FlagAssignment) must fail fast at the
    boundary instead of crashing inside the pure orchestrator."""

    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {
        "configurable": {
            "active_learning_assignment": {"variant": "treatment"},  # dict, not FlagAssignment
            "active_learning_examples": [example],
        }
    }
    result = agent._inject_active_learning_few_shot(state, config=config)
    assert result is state


def test_combined_hook_pass_through_when_feature_off(
    agent: Agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without AL config keys, the combined hook behaves exactly as before."""

    monkeypatch.setattr(agent, "_add_timestamp_to_tool_messages", lambda state: None)
    monkeypatch.setattr(
        agent, "_inject_long_term_memory", lambda state, config=None: state
    )
    monkeypatch.setattr(
        agent, "_filter_short_term_memory", lambda state: {"messages": state["messages"]}
    )
    monkeypatch.setattr(
        agent,
        "_inject_thread_id_in_user_id_params",
        lambda state, config=None: state,
    )

    state: dict[str, Any] = {"messages": [HumanMessage(content="hi")]}
    config = {"configurable": {"thread_id": "t1"}}
    result = agent._combined_pre_model_hook(state, config=config)
    messages = result.get("messages") or result.get("llm_input_messages") or []
    # No SystemMessage added.
    assert all(not isinstance(m, SystemMessage) for m in messages)
    assert len(messages) == 1
