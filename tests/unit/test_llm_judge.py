"""Unit tests for ``engine.judges.llm_judge`` (Tier-0 judge-infra, ADR-038).

MECHANICS only — the LLM is injected as a fake ``JudgeModel``, so these test
prompt assembly, panel completeness, the downstream contract, and fail-fast.
They do NOT validate judge accuracy (that needs ≥50 human annotations; a
production gate, not a dev test — ADR-038).

Coverage:
- judge_all returns the complete 3-dimension panel.
- each judge receives its OWN rubric (independence — 3 distinct system prompts).
- per-dimension user content: faithfulness carries context, tool_misuse carries
  tool calls, policy carries neither.
- to_judge_verdicts projects to the {dim -> bool} map.
- end-to-end interop: the panel feeds adjudication.PromptOutcome cleanly.
- JudgeVerdict validation rejects out-of-range confidence / empty rationale.
- fail-fast: unknown dimension, non-JudgeVerdict model return.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.adversarial.adjudication import PromptOutcome, is_bypass_confirmed
from engine.judges.llm_judge import (
    JUDGE_DIMENSIONS,
    JudgeCase,
    JudgeError,
    JudgeVerdict,
    ToolCall,
    judge_all,
    run_judge,
    to_judge_verdicts,
)


class _RecordingJudge:
    """Fake JudgeModel: records every (system_prompt, user_content) and returns
    a canned verdict — by rubric if a map is given, else a default."""

    def __init__(
        self,
        default: JudgeVerdict | None = None,
        by_rubric: dict[str, JudgeVerdict] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._default = default or JudgeVerdict(verdict=False, rationale="clean", confidence=0.9)
        self._by_rubric = by_rubric

    def complete(self, system_prompt: str, user_content: str) -> JudgeVerdict:
        self.calls.append((system_prompt, user_content))
        if self._by_rubric is not None:
            return self._by_rubric[system_prompt]
        return self._default


def _case(**overrides) -> JudgeCase:
    base = dict(
        prompt="Qual o prazo do IPTU?",
        bot_output="O prazo é 10 de março.",
        prompt_id="p1",
        category="T1",
    )
    base.update(overrides)
    return JudgeCase(**base)


# ---------- judge_all panel ----------


def test_judge_all_returns_complete_panel():
    panel = judge_all(_case(), _RecordingJudge())
    assert set(panel) == set(JUDGE_DIMENSIONS)
    assert all(isinstance(v, JudgeVerdict) for v in panel.values())


def test_each_judge_gets_its_own_rubric():
    fake = _RecordingJudge()
    judge_all(_case(), fake)
    rubrics_used = {system_prompt for system_prompt, _ in fake.calls}
    assert len(rubrics_used) == len(JUDGE_DIMENSIONS)  # 3 distinct rubrics → independent judges


# ---------- per-dimension user content ----------


def test_faithfulness_content_includes_source_context():
    fake = _RecordingJudge()
    run_judge(_case(source_context="Prazo oficial: 28 de fevereiro."), "faithfulness", fake)
    _, user_content = fake.calls[0]
    assert "CONTEXTO/FONTE" in user_content
    assert "28 de fevereiro" in user_content


def test_faithfulness_content_marks_missing_context():
    fake = _RecordingJudge()
    run_judge(_case(source_context=None), "faithfulness", fake)
    assert "nenhum contexto" in fake.calls[0][1]


def test_tool_misuse_content_includes_called_args_and_expected_tools():
    fake = _RecordingJudge()
    run_judge(
        _case(
            tool_calls=(ToolCall("delete_account", '{"id": 42}'),),
            expected_tools=("lookup_status",),
        ),
        "tool_misuse",
        fake,
    )
    user_content = fake.calls[0][1]
    assert "delete_account" in user_content
    assert '{"id": 42}' in user_content  # arguments reach the judge (T6 hijacked-args)
    assert "lookup_status" in user_content


def test_policy_content_omits_context_and_tools():
    fake = _RecordingJudge()
    run_judge(_case(source_context="secret", tool_calls=(ToolCall("x"),)), "policy", fake)
    user_content = fake.calls[0][1]
    assert "CONTEXTO/FONTE" not in user_content
    assert "FERRAMENTAS CHAMADAS" not in user_content


# ---------- downstream contract / interop ----------


def test_to_judge_verdicts_projects_to_bool_map():
    panel = judge_all(_case(), _RecordingJudge(JudgeVerdict(verdict=True, rationale="r", confidence=0.7)))
    verdicts = to_judge_verdicts(panel)
    assert verdicts == {dim: True for dim in JUDGE_DIMENSIONS}
    assert all(isinstance(value, bool) for value in verdicts.values())


def test_panel_feeds_adjudication_prompt_outcome():
    # faithfulness + policy fail, tool_misuse clean → 2/3 → bypass confirmed.
    from engine.judges.llm_judge import FAITHFULNESS_RUBRIC, POLICY_RUBRIC, TOOL_MISUSE_RUBRIC

    fail = JudgeVerdict(verdict=True, rationale="fail", confidence=0.8)
    ok = JudgeVerdict(verdict=False, rationale="ok", confidence=0.8)
    fake = _RecordingJudge(by_rubric={FAITHFULNESS_RUBRIC: fail, POLICY_RUBRIC: fail, TOOL_MISUSE_RUBRIC: ok})

    case = _case()
    verdicts = to_judge_verdicts(judge_all(case, fake))
    outcome = PromptOutcome(prompt_id=case.prompt_id, category=case.category, judge_verdicts=verdicts)
    assert is_bypass_confirmed(outcome, JUDGE_DIMENSIONS) is True


# ---------- JudgeVerdict validation (boundary) ----------


@pytest.mark.parametrize("bad_confidence", [1.5, -0.1])
def test_verdict_rejects_out_of_range_confidence(bad_confidence):
    with pytest.raises(ValidationError):
        JudgeVerdict(verdict=True, rationale="r", confidence=bad_confidence)


def test_verdict_rejects_empty_rationale():
    with pytest.raises(ValidationError):
        JudgeVerdict(verdict=True, rationale="", confidence=0.5)


# ---------- fail-fast ----------


def test_run_judge_unknown_dimension_raises():
    with pytest.raises(JudgeError, match="unknown judge dimension"):
        run_judge(_case(), "sentiment", _RecordingJudge())  # type: ignore[arg-type]


def test_run_judge_non_verdict_return_raises():
    class _BadModel:
        def complete(self, system_prompt: str, user_content: str):
            return {"verdict": True}  # wrong type

    with pytest.raises(JudgeError, match="expected JudgeVerdict"):
        run_judge(_case(), "faithfulness", _BadModel())  # type: ignore[arg-type]
