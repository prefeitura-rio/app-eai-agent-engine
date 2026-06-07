"""Local deterministic eval for the luminaria dynamic prompt gate.

This intentionally does not instantiate Agent and does not call Gateway,
Reasoning Engine, Vertex, MCP, Postgres, BigQuery, or GitHub Actions. It checks
the local code path that decides whether the heavy `reparo_luminaria`
interactive prompt is injected into a turn.

Run:
  uv run python scripts/local_luminaria_eval.py
  uv run python scripts/local_luminaria_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from engine.agent import (
    INTERACTIVE_RESPONSE_PROMPT,
    _inject_interactive_response_prompt,
    _should_inject_interactive_response_prompt,
)
from engine.luminaria_interactive_prompt import interactive_response_dynamic_enabled
from engine.session_boundary import CLOSE_DIRECTIVE
from src.prompt_modules import compose, interactive_response


@dataclass(frozen=True)
class GateCase:
    id: str
    messages: list[Any]
    expected: bool
    reason: str


@dataclass(frozen=True)
class CheckResult:
    id: str
    passed: bool
    expected: Any
    actual: Any
    reason: str


def _flow_submission_text() -> str:
    return (
        "[SYSTEM] O cidadao preencheu o formulario WhatsApp. Dados recebidos: "
        '{"defect_type":"Apagada","qty_pattern":"uma","location":"Rua"}. '
        "ACAO OBRIGATORIA: Chame a ferramenta multi_step_service imediatamente "
        "com service_name='reparo_luminaria' e payload contendo os dados recebidos "
        "(adicione _source='whatsapp_flow')."
    )


def _gate_cases() -> list[GateCase]:
    positives = [
        ("explicit_luminaria", "A luminaria da minha rua esta apagada"),
        ("rioluz_wire_hazard", "Tem fio caido com faisca perto do poste da Rioluz"),
        ("public_lighting", "A iluminacao publica falhou na minha rua"),
        ("public_light_square", "A luz da praca apagou"),
        ("lamp_on_post", "A lampada do poste queimou"),
        ("fallen_post", "O poste caiu com fios expostos"),
        ("shock_wire", "Tem cabo caido na rua dando choque"),
        ("street_dark", "A rua esta escura faz dois dias"),
        ("street_lighting", "A iluminacao da minha rua apagou"),
        ("repair_request", "Quero abrir reparo de luz publica na Rua A, 10"),
    ]
    negatives = [
        ("tree_pruning", "Como faco para solicitar poda de arvore?"),
        ("tree_near_post", "Preciso podar uma arvore encostando no poste da rua"),
        ("internet_cable_home", "Meu cabo de internet arrebentou dentro de casa"),
        ("internet_cable_street", "Meu cabo de internet caiu na rua"),
        ("bedroom_lamp", "A lampada do quarto queimou"),
        ("living_room_light", "A iluminacao da sala esta ruim"),
        ("home_power_outage", "A luz acabou na minha casa"),
        ("traffic_light", "O semaforo apagou no cruzamento"),
        ("phone_wire", "O fio do telefone caiu na calcada"),
        ("tv_cable", "A tv a cabo parou e o cabo esta solto"),
    ]

    cases = [
        GateCase(
            id=case_id,
            messages=[HumanMessage(content=text)],
            expected=True,
            reason="turno atual e de reparo/risco de iluminacao publica",
        )
        for case_id, text in positives
    ]
    cases.extend(
        GateCase(
            id=case_id,
            messages=[HumanMessage(content=text)],
            expected=False,
            reason="servico ou contexto nao deve receber prompt de luminaria",
        )
        for case_id, text in negatives
    )
    cases.extend(
        [
            GateCase(
                id="latest_turn_wins_negative",
                messages=[
                    HumanMessage(content="A luminaria da rua esta apagada"),
                    AIMessage(content="[Flow de luminaria]"),
                    HumanMessage(content="Agora quero solicitar poda de arvore"),
                ],
                expected=False,
                reason="historico antigo de luminaria nao contamina outro servico",
            ),
            GateCase(
                id="latest_turn_wins_positive",
                messages=[
                    HumanMessage(content="Como faco para solicitar poda?"),
                    AIMessage(content="Posso orientar."),
                    HumanMessage(content="Tambem tem uma luminaria apagada na rua"),
                ],
                expected=True,
                reason="turno atual de luminaria deve ativar o prompt dinamico",
            ),
            GateCase(
                id="multipart_text",
                messages=[
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "A luminaria da rua apagou"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://example/img"},
                            },
                        ]
                    )
                ],
                expected=True,
                reason="conteudo multimodal com texto relevante deve ativar gate",
            ),
            GateCase(
                id="flow_submission",
                messages=[
                    HumanMessage(content="A luminaria da rua esta apagada"),
                    AIMessage(content="[Flow de luminaria]"),
                    HumanMessage(content=_flow_submission_text()),
                ],
                expected=False,
                reason="submissao de WhatsApp Flow ja e tratada por outro modulo",
            ),
        ]
    )
    return cases


def _evaluate_gate() -> list[CheckResult]:
    results = []
    for case in _gate_cases():
        actual = _should_inject_interactive_response_prompt(case.messages)
        results.append(
            CheckResult(
                id=f"gate::{case.id}",
                passed=actual == case.expected,
                expected=case.expected,
                actual=actual,
                reason=case.reason,
            )
        )
    return results


def _evaluate_prompt_contract() -> list[CheckResult]:
    augmented_prompt, version = compose("BASE", "v0")
    checks = [
        (
            "dynamic_enabled",
            True,
            interactive_response_dynamic_enabled(),
            "kill-switch local deve deixar prompt dinamico ativo",
        ),
        (
            "not_global_prompt",
            False,
            interactive_response.MODULE_PROMPT in augmented_prompt,
            "prompt pesado nao deve entrar no system prompt global",
        ),
        (
            "not_global_version",
            False,
            "interactive_response" in version,
            "versao global nao deve carregar sufixo interactive_response",
        ),
        (
            "service_scope",
            True,
            "reparo_luminaria" in INTERACTIVE_RESPONSE_PROMPT,
            "prompt dinamico deve continuar escopado ao servico certo",
        ),
        (
            "wire_defect_mapping",
            True,
            'defect_type="Danificada"' in INTERACTIVE_RESPONSE_PROMPT,
            "furto/cabo/fios deve mapear para defeito canonico do Flow",
        ),
        (
            "out_of_scope_route",
            True,
            "Fora de escopo" in INTERACTIVE_RESPONSE_PROMPT,
            "prompt deve preservar rota de fora de escopo antes do Flow",
        ),
    ]
    return [
        CheckResult(
            id=f"contract::{check_id}",
            passed=actual == expected,
            expected=expected,
            actual=actual,
            reason=reason,
        )
        for check_id, expected, actual, reason in checks
    ]


def _evaluate_injection() -> list[CheckResult]:
    close = SystemMessage(content=CLOSE_DIRECTIVE)
    messages = [
        SystemMessage(content="memoria"),
        HumanMessage(content="A luminaria apagou, era so isso"),
        close,
    ]
    injected = _inject_interactive_response_prompt(messages)
    order = [type(message).__name__ for message in injected]

    already_injected = [
        SystemMessage(content="memoria"),
        SystemMessage(content=INTERACTIVE_RESPONSE_PROMPT),
        HumanMessage(content="A luminaria apagou"),
    ]
    idempotent = _inject_interactive_response_prompt(already_injected)

    checks = [
        (
            "order",
            ["SystemMessage", "SystemMessage", "HumanMessage", "SystemMessage"],
            order,
            "prompt dinamico entra apos sistemas iniciais e antes da conversa",
        ),
        (
            "content_position",
            True,
            injected[1].content == INTERACTIVE_RESPONSE_PROMPT,
            "prompt injetado deve ser exatamente o modulo de luminaria",
        ),
        (
            "trailing_directive_precedence",
            True,
            injected[-1] is close,
            "diretiva transitoria final deve manter maior precedencia",
        ),
        (
            "idempotent",
            True,
            idempotent is already_injected,
            "nao deve duplicar prompt se ele ja estiver presente",
        ),
    ]
    return [
        CheckResult(
            id=f"injection::{check_id}",
            passed=actual == expected,
            expected=expected,
            actual=actual,
            reason=reason,
        )
        for check_id, expected, actual, reason in checks
    ]


def run_eval() -> dict[str, Any]:
    checks = [
        *_evaluate_gate(),
        *_evaluate_prompt_contract(),
        *_evaluate_injection(),
    ]
    failures = [check for check in checks if not check.passed]
    groups: dict[str, dict[str, Any]] = {}
    for check in checks:
        group = check.id.split("::", 1)[0]
        current = groups.setdefault(group, {"total": 0, "passed": 0})
        current["total"] += 1
        current["passed"] += int(check.passed)
    for data in groups.values():
        data["score"] = data["passed"] / data["total"] if data["total"] else 0.0

    return {
        "name": "local_luminaria_eval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "offline": True,
        "calls_gateway": False,
        "calls_reasoning_engine": False,
        "calls_vertex": False,
        "calls_mcp": False,
        "dynamic_enabled": interactive_response_dynamic_enabled(),
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "score": (len(checks) - len(failures)) / len(checks),
            "groups": groups,
        },
        "checks": [check.__dict__ for check in checks],
    }


def _print_human(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("local_luminaria_eval")
    print(f"  offline: {result['offline']}")
    print(f"  gateway: {result['calls_gateway']}")
    print(f"  reasoning_engine: {result['calls_reasoning_engine']}")
    print(f"  vertex: {result['calls_vertex']}")
    print(f"  mcp: {result['calls_mcp']}")
    print(
        "  score: "
        f"{summary['passed']}/{summary['total']} "
        f"({summary['score']:.2%})"
    )
    for group, data in summary["groups"].items():
        print(
            f"  {group}: {data['passed']}/{data['total']} "
            f"({data['score']:.2%})"
        )
    failures = [check for check in result["checks"] if not check["passed"]]
    if not failures:
        print("PASS")
        return
    print("FAIL")
    for failure in failures:
        print(
            f"  - {failure['id']}: expected={failure['expected']!r} "
            f"actual={failure['actual']!r} ({failure['reason']})"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local deterministic luminaria eval."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the human summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON result.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_eval()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    if args.json:
        print(payload)
    else:
        _print_human(result)
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
