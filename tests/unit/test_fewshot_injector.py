"""Unit tests for ``engine.active_learning.fewshot_injector``.

Coverage targets:
- Empty input → no message (caller can short-circuit cheaply).
- Single example renders preamble + one Q/A pair.
- Multiple examples interleave with the separator (no leading/trailing sep).
- Render is deterministic: identical input yields byte-identical output.
- SystemMessage carries the rendered block verbatim as `content`.
"""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.messages import SystemMessage

from engine.active_learning.fewshot_injector import (
    BOT_PREFIX,
    CITIZEN_PREFIX,
    EXAMPLE_SEPARATOR,
    PREAMBLE,
    FewShotExample,
    build_few_shot_message,
    render_few_shot_block,
)


def test_render_empty_returns_empty_string():
    assert render_few_shot_block([]) == ""


def test_build_message_empty_returns_none():
    assert build_few_shot_message([]) is None


def test_render_single_example_contains_preamble_and_pair():
    block = render_few_shot_block(
        [FewShotExample(citizen_turn="Cadê meu IPTU?", bot_turn="O IPTU está em ...")]
    )
    assert PREAMBLE in block
    assert f"{CITIZEN_PREFIX} Cadê meu IPTU?" in block
    assert f"{BOT_PREFIX} O IPTU está em ..." in block
    # Single-example invariant: no separator should appear.
    assert EXAMPLE_SEPARATOR not in block


def test_render_multiple_examples_uses_separator_between():
    examples = [
        FewShotExample(citizen_turn="q1", bot_turn="a1"),
        FewShotExample(citizen_turn="q2", bot_turn="a2"),
        FewShotExample(citizen_turn="q3", bot_turn="a3"),
    ]
    block = render_few_shot_block(examples)
    # Exactly N-1 separators for N examples.
    assert block.count(EXAMPLE_SEPARATOR) == 2
    # No leading or trailing separator.
    assert not block.startswith(EXAMPLE_SEPARATOR)
    assert not block.endswith(EXAMPLE_SEPARATOR)


def test_render_is_deterministic():
    examples = [
        FewShotExample(citizen_turn="ola", bot_turn="oi"),
        FewShotExample(citizen_turn="ajuda", bot_turn="claro"),
    ]
    assert render_few_shot_block(examples) == render_few_shot_block(examples)


def test_build_message_returns_system_message_with_rendered_content():
    examples = [FewShotExample(citizen_turn="q", bot_turn="a")]
    message = build_few_shot_message(examples)
    assert isinstance(message, SystemMessage)
    assert message.content == render_few_shot_block(examples)


def test_render_preserves_order():
    examples = [
        FewShotExample(citizen_turn="first", bot_turn="A"),
        FewShotExample(citizen_turn="second", bot_turn="B"),
    ]
    block = render_few_shot_block(examples)
    assert block.index("first") < block.index("second")


def test_frozen_dataclass_immutable():
    example = FewShotExample(citizen_turn="q", bot_turn="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        example.citizen_turn = "tampered"  # type: ignore[misc]


@pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
def test_empty_or_whitespace_citizen_turn_rejected(bad_value):
    with pytest.raises(ValueError, match="citizen_turn"):
        FewShotExample(citizen_turn=bad_value, bot_turn="a")


@pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
def test_empty_or_whitespace_bot_turn_rejected(bad_value):
    with pytest.raises(ValueError, match="bot_turn"):
        FewShotExample(citizen_turn="q", bot_turn=bad_value)


def test_separator_in_citizen_turn_rejected():
    with pytest.raises(ValueError, match="separator"):
        FewShotExample(citizen_turn=f"q{EXAMPLE_SEPARATOR}injection", bot_turn="a")


def test_separator_in_bot_turn_rejected():
    with pytest.raises(ValueError, match="separator"):
        FewShotExample(citizen_turn="q", bot_turn=f"a{EXAMPLE_SEPARATOR}injection")
