"""Tests for ``Agent._build_chat_vertex_ai_with_cache_fallback``.

Goal: if ``ChatVertexAI(cached_content=...)`` rejects the cache resource
(stale TTL, deleted out-of-band, schema drift), the helper must:

1. Log a warning and invalidate the manager's record (so the next setup
   round mints a fresh cache).
2. Retry ``ChatVertexAI(**base_llm_kwargs)`` *without* the cache kwarg so
   the agent degrades to implicit caching instead of failing process
   setup for its lifetime (codex P1 finding).

We do not import ``Agent`` directly — its module init triggers ChatVertexAI
construction in unrelated paths. Instead we instantiate the bound method
via a minimal duck-typed object so the test stays light.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class _FakeAgentBase:
    """Subset of ``Agent`` needed by ``_build_chat_vertex_ai_with_cache_fallback``."""

    def __init__(self, manager=None):
        self._gemini_cache_manager = manager


def _build_helper_bound(agent_stub):
    """Bind the real method onto our stub so we exercise the actual code."""
    from engine.agent import Agent

    return Agent._build_chat_vertex_ai_with_cache_fallback.__get__(agent_stub, type(agent_stub))


def test_no_cache_passes_base_kwargs_through():
    fake_llm = object()
    with patch("engine.agent.ChatVertexAI", return_value=fake_llm) as chat_mock:
        helper = _build_helper_bound(_FakeAgentBase())
        result = helper(base_llm_kwargs={"model_name": "gemini-2.5-flash"}, cached_content=None)
    assert result is fake_llm
    chat_mock.assert_called_once_with(model_name="gemini-2.5-flash")


def test_cache_used_when_chat_vertex_accepts_it():
    fake_llm = object()
    with patch("engine.agent.ChatVertexAI", return_value=fake_llm) as chat_mock:
        helper = _build_helper_bound(_FakeAgentBase())
        result = helper(
            base_llm_kwargs={"model_name": "gemini-2.5-flash"},
            cached_content="cachedContents/abc",
        )
    assert result is fake_llm
    chat_mock.assert_called_once_with(
        model_name="gemini-2.5-flash",
        cached_content="cachedContents/abc",
    )


def test_cache_failure_falls_back_to_no_cache_and_invalidates_manager():
    """When ChatVertexAI rejects the cache, we must retry without it and
    flush the manager so the next ``_create_react_agent`` mints anew.
    """
    fake_llm = object()
    chat_mock = MagicMock(side_effect=[RuntimeError("invalid cached_content"), fake_llm])
    fake_manager = MagicMock()
    with patch("engine.agent.ChatVertexAI", chat_mock):
        helper = _build_helper_bound(_FakeAgentBase(manager=fake_manager))
        result = helper(
            base_llm_kwargs={"model_name": "gemini-2.5-flash"},
            cached_content="cachedContents/stale",
        )
    assert result is fake_llm
    # First call attempted with cache, second without.
    assert chat_mock.call_count == 2
    first_call_kwargs = chat_mock.call_args_list[0].kwargs
    assert first_call_kwargs["cached_content"] == "cachedContents/stale"
    second_call_kwargs = chat_mock.call_args_list[1].kwargs
    assert "cached_content" not in second_call_kwargs
    # The manager was invalidated so next setup rebuilds the cache.
    fake_manager.invalidate.assert_called_once()


def test_cache_failure_with_no_manager_still_recovers():
    """If the manager is None (cache flag was just turned off) but a stale
    name was passed in, we still must retry without raising.
    """
    fake_llm = object()
    chat_mock = MagicMock(side_effect=[RuntimeError("nope"), fake_llm])
    with patch("engine.agent.ChatVertexAI", chat_mock):
        helper = _build_helper_bound(_FakeAgentBase(manager=None))
        result = helper(
            base_llm_kwargs={"model_name": "gemini-2.5-flash"},
            cached_content="cachedContents/whatever",
        )
    assert result is fake_llm
    assert chat_mock.call_count == 2


def test_manager_invalidate_failure_does_not_propagate():
    """If invalidate() raises (e.g. Vertex delete returns 5xx), the
    fallback path must still successfully build the LLM.
    """
    fake_llm = object()
    chat_mock = MagicMock(side_effect=[RuntimeError("bad cache"), fake_llm])
    fake_manager = MagicMock()
    fake_manager.invalidate.side_effect = RuntimeError("delete failed")
    with patch("engine.agent.ChatVertexAI", chat_mock):
        helper = _build_helper_bound(_FakeAgentBase(manager=fake_manager))
        result = helper(
            base_llm_kwargs={"model_name": "gemini-2.5-flash"},
            cached_content="cachedContents/abc",
        )
    assert result is fake_llm
    fake_manager.invalidate.assert_called_once()
