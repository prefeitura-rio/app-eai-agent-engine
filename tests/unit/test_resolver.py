"""Unit tests for ``engine.active_learning.resolver``.

Coverage targets:
- NullRetriever always returns no examples.
- Resolver returns (None, []) when flag service is unavailable.
- Resolver returns (control_assignment, []) for control variant — never
  calls the retriever.
- Resolver returns (treatment_assignment, examples) for treatment variant.
- Retriever failure degrades to (treatment_assignment, []) — never raises.
- ResolvedActiveLearning.as_config_overrides renders the right keys.
- top_k and flag_name are threaded into the retriever / flag client calls.
"""

from __future__ import annotations

import pytest

from engine.active_learning.fewshot_injector import FewShotExample
from engine.active_learning.flag_client import FlagAssignment
from engine.active_learning.resolver import (
    DEFAULT_TOP_K,
    ActiveLearningResolver,
    NullRetriever,
    ResolvedActiveLearning,
)


class _FakeFlagClient:
    def __init__(self, assignment: FlagAssignment | None):
        self._assignment = assignment
        self.calls: list[tuple[str, str]] = []

    async def assign(self, flag_name: str, user_id: str) -> FlagAssignment | None:
        self.calls.append((flag_name, user_id))
        return self._assignment


class _RecordingRetriever:
    def __init__(self, examples: list[FewShotExample]):
        self._examples = examples
        self.calls: list[tuple[str, int]] = []

    async def retrieve(self, query: str, k: int) -> list[FewShotExample]:
        self.calls.append((query, k))
        return self._examples


class _RaisingRetriever:
    async def retrieve(self, query: str, k: int) -> list[FewShotExample]:
        raise RuntimeError("index unavailable")


def _treatment() -> FlagAssignment:
    return FlagAssignment(flag="active_learning_v1", variant="treatment", user_id="u-1")


def _control() -> FlagAssignment:
    return FlagAssignment(flag="active_learning_v1", variant="control", user_id="u-2")


def _example() -> FewShotExample:
    return FewShotExample(citizen_turn="q", bot_turn="a")


@pytest.mark.asyncio
async def test_null_retriever_returns_empty():
    retriever = NullRetriever()
    assert await retriever.retrieve("anything", 3) == []


@pytest.mark.asyncio
async def test_resolve_flag_unavailable_returns_none_and_empty():
    resolver = ActiveLearningResolver(flag_client=_FakeFlagClient(None))
    result = await resolver.resolve("u-1", "query")
    assert result.assignment is None
    assert result.examples == []


@pytest.mark.asyncio
async def test_resolve_control_variant_skips_retriever():
    retriever = _RecordingRetriever([_example()])
    resolver = ActiveLearningResolver(
        flag_client=_FakeFlagClient(_control()), retriever=retriever
    )
    result = await resolver.resolve("u-2", "query")
    assert result.assignment is not None
    assert result.assignment.variant == "control"
    assert result.examples == []
    assert retriever.calls == []  # retriever never invoked for control


@pytest.mark.asyncio
async def test_resolve_treatment_returns_examples():
    examples = [_example(), _example()]
    retriever = _RecordingRetriever(examples)
    resolver = ActiveLearningResolver(
        flag_client=_FakeFlagClient(_treatment()), retriever=retriever
    )
    result = await resolver.resolve("u-1", "minha query")
    assert result.assignment is not None
    assert result.assignment.variant == "treatment"
    assert result.examples == examples
    assert retriever.calls == [("minha query", DEFAULT_TOP_K)]


@pytest.mark.asyncio
async def test_resolve_retriever_failure_degrades_to_empty():
    resolver = ActiveLearningResolver(
        flag_client=_FakeFlagClient(_treatment()), retriever=_RaisingRetriever()
    )
    result = await resolver.resolve("u-1", "query")
    # Assignment preserved (still treatment) but examples empty — no raise.
    assert result.assignment is not None
    assert result.assignment.variant == "treatment"
    assert result.examples == []


@pytest.mark.asyncio
async def test_default_retriever_is_null():
    resolver = ActiveLearningResolver(flag_client=_FakeFlagClient(_treatment()))
    result = await resolver.resolve("u-1", "query")
    assert result.examples == []  # NullRetriever default


@pytest.mark.asyncio
async def test_custom_flag_name_and_top_k_threaded():
    flag_client = _FakeFlagClient(_treatment())
    retriever = _RecordingRetriever([_example()])
    resolver = ActiveLearningResolver(
        flag_client=flag_client,
        retriever=retriever,
        flag_name="custom_flag",
        top_k=5,
    )
    await resolver.resolve("u-9", "q")
    assert flag_client.calls == [("custom_flag", "u-9")]
    assert retriever.calls == [("q", 5)]


def test_as_config_overrides_renders_keys():
    resolved = ResolvedActiveLearning(assignment=_treatment(), examples=[_example()])
    overrides = resolved.as_config_overrides()
    assert set(overrides.keys()) == {
        "active_learning_assignment",
        "active_learning_examples",
    }
    assert overrides["active_learning_assignment"] is resolved.assignment
    assert overrides["active_learning_examples"] is resolved.examples


def test_as_config_overrides_none_assignment():
    resolved = ResolvedActiveLearning(assignment=None, examples=[])
    overrides = resolved.as_config_overrides()
    assert overrides["active_learning_assignment"] is None
    assert overrides["active_learning_examples"] == []
