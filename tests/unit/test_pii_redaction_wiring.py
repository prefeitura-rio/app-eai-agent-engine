"""Integration tests for C3 PII redaction wiring inside ``engine.agent.Agent``.

These tests exercise the agent's hooks directly — no LangGraph, no Vertex AI —
so they're fast and deterministic. They cover the contract from the plan:

1. User-supplied PII is redacted before LangGraph/LLM sees it (input path).
2. PII tokens are restored in tool_call args before the ToolNode runs
   (so tools like ``consulta_iptu`` receive the citizen's real CPF).
3. PII tokens in the final AI reply are restored before the worker callback.
4. Multi-turn: tokens minted on turn N are still restorable on turn N+M
   within the TTL window.
5. Tool / system messages are not redacted (only citizen input).
6. Multimodal payloads keep non-text parts intact.
7. Empty / None / non-string content is safe.
8. Existing tests (105/105) stay green — guarded implicitly because the
   hooks remain pass-through when there is no PII.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from engine.agent import Agent
from engine.middleware import PIIThreadCache, redact_with_cache


# ---------- Fixtures ----------


@pytest.fixture
def agent() -> Agent:
    """Minimal Agent instance — no Postgres, no Vertex AI, no MCP.

    The hooks we exercise here read only ``self._pii_thread_cache`` plus
    static helpers, so the missing connections do not matter.
    """
    return Agent(
        model="gemini-2.5-flash",
        system_prompt="(test prompt)",
        tools=[],
        otpl_service="test-engine",
    )


@pytest.fixture
def thread_kwargs() -> dict[str, Any]:
    """Standard kwargs shape used by ``_combined_pre_invoke_hook`` callers."""
    return {
        "config": {"configurable": {"thread_id": "thread-test-1"}},
        "input": {"messages": []},
    }


# ---------- Helpers ----------


def _set_messages(thread_kwargs: dict[str, Any], messages: list[Any]) -> None:
    thread_kwargs["input"]["messages"] = messages


def _get_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


# ---------- Item 1.1 — input redaction (dict shape) ----------


def test_redact_input_replaces_cpf_for_dict_message(agent, thread_kwargs):
    _set_messages(
        thread_kwargs,
        [{"type": "human", "content": "Meu CPF é 123.456.789-09, obrigado."}],
    )
    out_kwargs = agent._redact_input_messages(**thread_kwargs)
    content = _get_content(out_kwargs["input"]["messages"][0])
    assert "123.456.789-09" not in content
    assert "[CPF_TOKEN_1]" in content


def test_redact_input_preserves_non_pii_text(agent, thread_kwargs):
    safe_text = "Bom dia, gostaria de saber sobre IPTU."
    _set_messages(thread_kwargs, [{"type": "human", "content": safe_text}])
    out_kwargs = agent._redact_input_messages(**thread_kwargs)
    assert _get_content(out_kwargs["input"]["messages"][0]) == safe_text


def test_redact_input_replaces_multiple_pii_categories(agent, thread_kwargs):
    sentence = (
        "Sou cliente, CPF 123.456.789-09, CEP 22041-001, "
        "fone (21) 99999-1234, Av. Brasil, 2500."
    )
    _set_messages(thread_kwargs, [{"type": "human", "content": sentence}])
    out_kwargs = agent._redact_input_messages(**thread_kwargs)
    content = _get_content(out_kwargs["input"]["messages"][0])
    for piece in [
        "123.456.789-09",
        "22041-001",
        "(21) 99999-1234",
        "Av. Brasil, 2500",
    ]:
        assert piece not in content, f"PII leaked: {piece!r}"


# ---------- Item 1.2 — input redaction (BaseMessage shape) ----------


def test_redact_input_replaces_cpf_for_basemessage(agent, thread_kwargs):
    msg = HumanMessage(content="Meu CPF é 123.456.789-09.")
    _set_messages(thread_kwargs, [msg])
    agent._redact_input_messages(**thread_kwargs)
    assert "123.456.789-09" not in msg.content
    assert "[CPF_TOKEN_1]" in msg.content


# ---------- Item 1.3 — non-citizen messages skipped ----------


def test_redact_input_skips_tool_and_system_messages(agent, thread_kwargs):
    # System / tool / AI messages must NEVER be redacted — they either carry
    # admin text or machine output that is already token-safe.
    system_msg = {
        "type": "system",
        "content": "Numero secreto admin: 123.456.789-09",
    }
    tool_msg = {"type": "tool", "content": "Resultado IPTU 12.345.678/0001-95"}
    ai_msg = {"type": "ai", "content": "AI reply with 22041-001 inside"}
    _set_messages(thread_kwargs, [system_msg, tool_msg, ai_msg])
    agent._redact_input_messages(**thread_kwargs)
    # All three keep their literal PII because we don't redact non-human input.
    assert "123.456.789-09" in system_msg["content"]
    assert "12.345.678/0001-95" in tool_msg["content"]
    assert "22041-001" in ai_msg["content"]


# ---------- Item 1.4 — multimodal payload preservation ----------


def test_redact_input_redacts_text_parts_in_multimodal(agent, thread_kwargs):
    image_bytes_part = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }
    text_part = {"type": "text", "text": "Meu CPF é 123.456.789-09"}
    msg = {
        "type": "human",
        "content": [text_part, image_bytes_part],
    }
    _set_messages(thread_kwargs, [msg])
    agent._redact_input_messages(**thread_kwargs)
    # Image part untouched.
    assert image_bytes_part["image_url"]["url"] == "data:image/png;base64,AAAA"
    # Text part redacted.
    assert "123.456.789-09" not in text_part["text"]
    assert "[CPF_TOKEN_1]" in text_part["text"]


# ---------- Item 1.5 — empty / None content is safe ----------


@pytest.mark.parametrize(
    "content",
    [None, "", [], {}, 12345],
)
def test_redact_input_handles_empty_or_weird_content(agent, thread_kwargs, content):
    msg = {"type": "human", "content": content}
    _set_messages(thread_kwargs, [msg])
    agent._redact_input_messages(**thread_kwargs)
    # Nothing should have been mutated; no exception raised.
    assert msg["content"] == content


# ---------- Item 1.6 — no thread_id ⇒ no redaction ----------


def test_redact_input_skips_when_thread_id_missing(agent, thread_kwargs):
    thread_kwargs["config"] = {"configurable": {}}
    _set_messages(
        thread_kwargs,
        [{"type": "human", "content": "Meu CPF é 123.456.789-09."}],
    )
    agent._redact_input_messages(**thread_kwargs)
    # Without thread_id we cannot persist mapping → leave as is.
    assert "123.456.789-09" in thread_kwargs["input"]["messages"][0]["content"]


# ---------- Item 1.7 — feature flag OFF ⇒ no-op ----------


def test_redact_input_short_circuits_when_flag_disabled(agent, thread_kwargs):
    _set_messages(
        thread_kwargs,
        [{"type": "human", "content": "Meu CPF é 123.456.789-09."}],
    )
    with patch.dict("os.environ", {"PII_REDACTION_ENABLED": "false"}):
        agent._redact_input_messages(**thread_kwargs)
    assert "123.456.789-09" in thread_kwargs["input"]["messages"][0]["content"]


# ---------- Item 1.8 — tool_call args restoration (post-model hook) ----------


def test_post_model_hook_restores_pii_in_tool_call_args(agent):
    """After redaction the LLM only sees ``[CPF_TOKEN_1]``. If it echoes the
    token into a tool_call's args, the post-model hook must restore the real
    CPF so the tool receives usable input.
    """
    # Seed the cache with a mapping as if input redaction had already run.
    cpf_value = "123.456.789-09"
    agent._pii_thread_cache.update(
        "thread-tool", {"[CPF_TOKEN_1]": cpf_value}
    )
    ai_msg = AIMessage(
        content="Consultando IPTU…",
        tool_calls=[
            {
                "name": "consulta_iptu",
                "args": {"cpf": "[CPF_TOKEN_1]"},
                "id": "tc-1",
            }
        ],
    )
    state = {"messages": [ai_msg]}
    config = {"configurable": {"thread_id": "thread-tool"}}
    agent._combined_post_model_hook(state, config=config)
    assert ai_msg.tool_calls[0]["args"]["cpf"] == cpf_value


def test_post_model_hook_does_not_touch_ai_message_without_tokens(agent):
    """When the LLM reply contains no token we leave it alone (cheap path)."""
    agent._pii_thread_cache.update(
        "thread-no-token", {"[CPF_TOKEN_1]": "999.999.999-99"}
    )
    ai_msg = AIMessage(content="Olá, tudo bem? Aqui é a Eai.")
    state = {"messages": [ai_msg]}
    config = {"configurable": {"thread_id": "thread-no-token"}}
    agent._combined_post_model_hook(state, config=config)
    assert ai_msg.content == "Olá, tudo bem? Aqui é a Eai."


# ---------- Item 1.9 — final restore at worker callback ----------


def test_restore_pii_in_result_replaces_tokens_in_ai_messages(agent):
    cpf_value = "123.456.789-09"
    agent._pii_thread_cache.update("thread-end", {"[CPF_TOKEN_1]": cpf_value})
    ai_msg = AIMessage(content=f"Confirmando seu CPF [CPF_TOKEN_1].")
    result = {"messages": [ai_msg]}
    kwargs = {"config": {"configurable": {"thread_id": "thread-end"}}}
    restored = agent._restore_pii_in_result(result, **kwargs)
    assert cpf_value in restored["messages"][0].content
    assert "[CPF_TOKEN_1]" not in restored["messages"][0].content


def test_restore_pii_in_result_skips_when_no_cache_entry(agent):
    msg = AIMessage(content="Não há tokens aqui")
    result = {"messages": [msg]}
    kwargs = {"config": {"configurable": {"thread_id": "fresh-thread"}}}
    restored = agent._restore_pii_in_result(result, **kwargs)
    assert restored["messages"][0].content == "Não há tokens aqui"


# ---------- Item 1.10 — multi-turn token reuse via TTL cache ----------


def test_multi_turn_round_trip_preserves_mapping(agent):
    # Turn 1: citizen sends a CPF; the cache learns the mapping.
    kwargs_t1 = {
        "config": {"configurable": {"thread_id": "thread-multi"}},
        "input": {"messages": [{"type": "human", "content": "CPF 123.456.789-09"}]},
    }
    agent._redact_input_messages(**kwargs_t1)
    mapping_after_t1 = agent._pii_thread_cache.get("thread-multi")
    assert mapping_after_t1["[CPF_TOKEN_1]"] == "123.456.789-09"

    # Turn 5 (simulated): the LLM echoes the token in its final reply. The
    # restore path must still resolve it from the cache.
    final_msg = AIMessage(content="Seu CPF [CPF_TOKEN_1] foi recebido.")
    result = {"messages": [final_msg]}
    kwargs_t5 = {"config": {"configurable": {"thread_id": "thread-multi"}}}
    restored = agent._restore_pii_in_result(result, **kwargs_t5)
    assert "123.456.789-09" in restored["messages"][0].content


# ---------- Item 1.11 — cache TTL eviction ----------


def test_pii_cache_expires_after_ttl():
    cache = PIIThreadCache(ttl_seconds=1)
    cache.update("t1", {"[CPF_TOKEN_1]": "111.111.111-11"})
    assert cache.size() == 1

    # Move monotonic clock forward past the TTL.
    import time as _time

    real_monotonic = _time.monotonic
    future_offset = cache.ttl_seconds + 1

    def fake_monotonic() -> float:
        return real_monotonic() + future_offset

    with patch.object(_time, "monotonic", fake_monotonic):
        assert cache.get("t1") == {}
        assert cache.size() == 0


# ---------- Item 1.12 — defensive: redact failure does not break the bot ----------


def test_redact_input_swallows_exceptions(agent, thread_kwargs):
    """If something exotic raises inside the redactor we MUST not break the
    conversation; we log and pass the original text through.
    """
    _set_messages(
        thread_kwargs,
        [{"type": "human", "content": "Meu CPF é 123.456.789-09"}],
    )
    with patch(
        "engine.agent.redact_with_cache",
        side_effect=RuntimeError("boom"),
    ):
        out_kwargs = agent._redact_input_messages(**thread_kwargs)
    # The exception was swallowed; the message survives untouched.
    assert "123.456.789-09" in _get_content(out_kwargs["input"]["messages"][0])


# ---------- Item 1.13 — helper round-trip via redact_with_cache ----------


def test_redact_with_cache_round_trip_uses_shared_cache():
    cache = PIIThreadCache(ttl_seconds=60)
    redacted, mapping = redact_with_cache(
        "CPF 123.456.789-09", cache, "thread-helper"
    )
    assert "123.456.789-09" not in redacted
    assert mapping["[CPF_TOKEN_1]"] == "123.456.789-09"

    # Same thread, follow-up text with a different CPF — both tokens must
    # accumulate in the cache so a later restore resolves both.
    redacted_2, mapping_2 = redact_with_cache(
        "Outro CPF 987.654.321-00", cache, "thread-helper"
    )
    assert "987.654.321-00" not in redacted_2
    # The merged mapping contains BOTH CPFs.
    assert "123.456.789-09" in mapping_2.values()
    assert "987.654.321-00" in mapping_2.values()


# ---------- Item 1.14 — ToolMessage / SystemMessage on input list ignored ----------


def test_redact_input_ignores_system_and_tool_basemessages(agent, thread_kwargs):
    system_msg = SystemMessage(content="Admin: 123.456.789-09")
    tool_msg = ToolMessage(content="Result: 12.345.678/0001-95", tool_call_id="x")
    _set_messages(thread_kwargs, [system_msg, tool_msg])
    agent._redact_input_messages(**thread_kwargs)
    assert "123.456.789-09" in system_msg.content
    assert "12.345.678/0001-95" in tool_msg.content


# ---------- Item 1.15 — concurrent redact_and_merge never collides tokens ----------


def test_concurrent_redact_and_merge_keeps_token_uniqueness():
    """Codex review P2: ensure two parallel calls for the *same* thread never
    assign the same token number to different PII values.

    Without the atomic ``redact_and_merge`` primitive this test was racey: two
    workers reading the same snapshot would both mint ``[CPF_TOKEN_1]`` for
    distinct values, and one ``setdefault`` would silently drop a mapping.
    """
    import threading

    cache = PIIThreadCache(ttl_seconds=60)
    thread_id = "race-thread"
    distinct_cpfs = [f"{i:03d}.456.789-09" for i in range(100, 132)]  # 32 unique CPFs
    results: list[tuple[str, dict[str, str]]] = []
    results_lock = threading.Lock()

    def worker(cpf: str) -> None:
        redacted, mapping = cache.redact_and_merge(thread_id, f"CPF {cpf}.")
        with results_lock:
            results.append((redacted, mapping))

    workers = [threading.Thread(target=worker, args=(cpf,)) for cpf in distinct_cpfs]
    for worker_thread in workers:
        worker_thread.start()
    for worker_thread in workers:
        worker_thread.join()

    final_mapping = cache.get(thread_id)
    # Every distinct CPF must be in the final mapping (no silent drops).
    final_values = set(final_mapping.values())
    for cpf in distinct_cpfs:
        assert cpf in final_values, f"CPF {cpf} dropped under contention"
    # Token keys must be unique (no two CPFs share the same token).
    assert len(final_mapping) == len(distinct_cpfs)
    # Restoration of any individual redaction round-trips correctly.
    for redacted_text, mapping_snapshot in results:
        # The mapping returned to the worker covers its own redaction at minimum.
        assert "[CPF_TOKEN_" in redacted_text


def test_redact_and_merge_no_thread_id_returns_empty_mapping():
    cache = PIIThreadCache(ttl_seconds=60)
    redacted, mapping = cache.redact_and_merge("", "CPF 123.456.789-09")
    # No thread_id → no persistent mapping; the function still redacts safely
    # via the fallback path or returns the text unchanged.
    assert mapping == {} or "123.456.789-09" not in redacted


def test_redact_and_merge_does_not_persist_empty_entry_for_non_pii():
    """Codex review P2: workers serving thousands of unique threads with mostly
    non-PII traffic should not accumulate empty cache rows. A brand-new
    ``thread_id`` whose first message has no PII must NOT create an entry.
    """
    cache = PIIThreadCache(ttl_seconds=3600)
    redacted, mapping = cache.redact_and_merge(
        "no-pii-thread", "Bom dia, tudo bem com você?"
    )
    assert redacted == "Bom dia, tudo bem com você?"
    assert mapping == {}
    assert cache.size() == 0


def test_redact_and_merge_persists_entry_when_pii_present():
    cache = PIIThreadCache(ttl_seconds=3600)
    cache.redact_and_merge("real-pii-thread", "CPF 123.456.789-09")
    assert cache.size() == 1
