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
    ActiveLearningResolver,
    FewShotExample,
    FlagAssignment,
    ResolvedActiveLearning,
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


# ---------- _latest_user_text ----------


def test_latest_user_text_from_human_message():
    graph_input = {"messages": [HumanMessage(content="minha pergunta")]}
    assert Agent._latest_user_text(graph_input) == "minha pergunta"


def test_latest_user_text_from_dict_message():
    graph_input = {"messages": [{"type": "human", "content": "via dict"}]}
    assert Agent._latest_user_text(graph_input) == "via dict"


def test_latest_user_text_returns_most_recent_human():
    graph_input = {
        "messages": [
            HumanMessage(content="primeira"),
            HumanMessage(content="mais recente"),
        ]
    }
    assert Agent._latest_user_text(graph_input) == "mais recente"


def test_latest_user_text_empty_when_no_messages():
    assert Agent._latest_user_text({"messages": []}) == ""
    assert Agent._latest_user_text({}) == ""
    assert Agent._latest_user_text("not-a-dict") == ""


def test_latest_user_text_safe_on_non_list_messages():
    """Truthy non-list messages must return '' not raise (e.g. int)."""

    assert Agent._latest_user_text({"messages": 123}) == ""
    assert Agent._latest_user_text({"messages": "a string"}) == ""
    assert Agent._latest_user_text({"messages": None}) == ""


# ---------- _resolve_active_learning_into_config ----------


def _resolver_returning(
    assignment: FlagAssignment | None, examples: list[FewShotExample]
) -> ActiveLearningResolver:
    class _StubResolver:
        async def resolve(self, user_id: str, query: str) -> ResolvedActiveLearning:
            return ResolvedActiveLearning(assignment=assignment, examples=examples)

    return _StubResolver()  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_resolution_noop_when_no_resolver(agent: Agent) -> None:
    kwargs = {
        "config": {"configurable": {"thread_id": "t1"}},
        "input": {"messages": [HumanMessage(content="hi")]},
    }
    result = await agent._resolve_active_learning_into_config(kwargs)
    assert result is kwargs  # untouched


@pytest.mark.asyncio
async def test_resolution_noop_when_no_thread_id(
    assignment_treatment: FlagAssignment, example: FewShotExample
) -> None:
    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt="(t)",
        tools=[],
        otpl_service="test-engine",
        active_learning_resolver=_resolver_returning(assignment_treatment, [example]),
    )
    kwargs = {
        "config": {"configurable": {}},  # no thread_id
        "input": {"messages": [HumanMessage(content="hi")]},
    }
    result = await agent._resolve_active_learning_into_config(kwargs)
    assert result is kwargs


@pytest.mark.asyncio
async def test_resolution_noop_when_no_query(
    assignment_treatment: FlagAssignment, example: FewShotExample
) -> None:
    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt="(t)",
        tools=[],
        otpl_service="test-engine",
        active_learning_resolver=_resolver_returning(assignment_treatment, [example]),
    )
    kwargs = {
        "config": {"configurable": {"thread_id": "t1"}},
        "input": {"messages": []},  # no human text
    }
    result = await agent._resolve_active_learning_into_config(kwargs)
    assert result is kwargs


@pytest.mark.asyncio
async def test_resolution_merges_overrides_into_config(
    assignment_treatment: FlagAssignment, example: FewShotExample
) -> None:
    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt="(t)",
        tools=[],
        otpl_service="test-engine",
        active_learning_resolver=_resolver_returning(assignment_treatment, [example]),
    )
    kwargs = {
        "config": {"configurable": {"thread_id": "t1", "checkpoint_ns": "ns"}},
        "input": {"messages": [HumanMessage(content="minha query")]},
    }
    result = await agent._resolve_active_learning_into_config(kwargs)
    configurable = result["config"]["configurable"]
    # Pre-existing keys preserved.
    assert configurable["thread_id"] == "t1"
    assert configurable["checkpoint_ns"] == "ns"
    # New AL keys merged.
    assert configurable["active_learning_assignment"] is assignment_treatment
    assert configurable["active_learning_examples"] == [example]
    # Original kwargs not mutated.
    assert "active_learning_assignment" not in kwargs["config"]["configurable"]


# ---------- Hot-path integration via async_query ----------


@pytest.mark.asyncio
async def test_async_query_runs_resolution_stage(
    assignment_treatment: FlagAssignment,
    example: FewShotExample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drives async_query end-to-end (graph stubbed) and proves the
    resolution stage enriches config before the graph is invoked.

    Guards against a future refactor dropping the resolution call from
    async_query."""

    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt="(t)",
        tools=[],
        otpl_service="test-engine",
        active_learning_resolver=_resolver_returning(assignment_treatment, [example]),
    )

    # Stub out the heavy machinery: pre-invoke hook passes kwargs through,
    # async setup is a no-op, and the graph captures the config it received.
    monkeypatch.setattr(agent, "_combined_pre_invoke_hook", lambda **kw: kw)

    async def _noop_setup():
        return None

    monkeypatch.setattr(agent, "_ensure_async_setup", _noop_setup)

    captured: dict[str, Any] = {}

    class _StubGraph:
        async def ainvoke(self, **kwargs):
            captured["config"] = kwargs.get("config")
            return {"messages": []}

    agent._graph = _StubGraph()
    monkeypatch.setattr(agent, "_filter_current_interaction", lambda result: result)
    monkeypatch.setattr(
        agent, "_restore_pii_in_result", lambda result, **kw: result
    )
    monkeypatch.setattr(agent, "_trace_conversation", lambda result, **kw: None)

    await agent.async_query(
        config={"configurable": {"thread_id": "t1"}},
        input={"messages": [HumanMessage(content="minha query")]},
    )

    configurable = captured["config"]["configurable"]
    assert configurable["active_learning_assignment"] is assignment_treatment
    assert configurable["active_learning_examples"] == [example]


@pytest.mark.asyncio
async def test_async_query_resolver_raise_does_not_break_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resolver that raises must NOT break async_query — the turn
    proceeds with the original (un-enriched) config."""

    class _BoomResolver:
        async def resolve(self, user_id: str, query: str):
            raise RuntimeError("boom")

    agent = Agent(
        model="gemini-2.5-flash",
        system_prompt="(t)",
        tools=[],
        otpl_service="test-engine",
        active_learning_resolver=_BoomResolver(),  # type: ignore[arg-type]
    )

    monkeypatch.setattr(agent, "_combined_pre_invoke_hook", lambda **kw: kw)

    async def _noop_setup():
        return None

    monkeypatch.setattr(agent, "_ensure_async_setup", _noop_setup)

    captured: dict[str, Any] = {}

    class _StubGraph:
        async def ainvoke(self, **kwargs):
            captured["config"] = kwargs.get("config")
            return {"messages": []}

    agent._graph = _StubGraph()
    monkeypatch.setattr(agent, "_filter_current_interaction", lambda result: result)
    monkeypatch.setattr(
        agent, "_restore_pii_in_result", lambda result, **kw: result
    )
    monkeypatch.setattr(agent, "_trace_conversation", lambda result, **kw: None)

    # Must not raise.
    await agent.async_query(
        config={"configurable": {"thread_id": "t1"}},
        input={"messages": [HumanMessage(content="q")]},
    )
    # Config reached the graph without AL keys (degraded to control).
    configurable = captured["config"]["configurable"]
    assert "active_learning_assignment" not in configurable


def test_async_query_methods_keep_error_interceptor():
    """Guard against decorator-misplacement regression: inserting helper
    methods must not steal the @interceptor from the async query
    entrypoints. The interceptor uses functools.wraps, so a decorated
    method exposes __wrapped__; the undecorated helpers do not."""

    assert hasattr(Agent.async_query, "__wrapped__")
    assert hasattr(Agent.async_stream_query, "__wrapped__")
    # The resolution helper is intentionally undecorated (it self-guards).
    assert not hasattr(Agent._resolve_active_learning_into_config, "__wrapped__")
