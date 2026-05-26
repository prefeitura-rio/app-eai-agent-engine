"""Smoke de ORQUESTRAÇÃO gov.br (local, Gemini real) — valida que o prompt module
``govbr_auth_gating`` faz o LLM gatear serviço restrito atrás de auth e NÃO gatear
serviço público.

  uv run python tests/govbr_orchestration_smoke.py

Roda SEM Engine/Postgres/Redis/Gateway — só precisa de GEMINI_API_KEY. Liga as
tools reais (govbr_auth_*) + um serviço restrito (consultar_multas) + um público
(horario_funcionamento) ao Gemini 2.5 Flash e observa os tool_calls.

NÃO testa o round-trip de token (precisa login gov.br humano + Redis). Testa só a
DECISÃO de tool-calling dado o prompt. O base prompt aqui é representativo
(mínimo), não o system prompt pleno de prod — logo é indicativo, não definitivo.
"""

from __future__ import annotations

import os
import sys

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from src.prompt_modules import govbr_auth_gating


@tool
def govbr_auth_status(user_number: str) -> dict:
    """Verifica se o cidadão possui autenticação gov.br válida."""
    return {}


@tool
def govbr_auth_init(user_number: str, service_context: str = "consulta_dados") -> dict:
    """Inicia o fluxo de autenticação gov.br; retorna a auth_url para o cidadão."""
    return {}


@tool
def govbr_logout(user_number: str) -> dict:
    """Faz logout do cidadão, revogando o token gov.br."""
    return {}


@tool
def consultar_multas(user_number: str) -> dict:
    """Consulta as multas de trânsito do cidadão (dado pessoal vinculado ao CPF)."""
    return {}


@tool
def horario_funcionamento(unidade: str) -> dict:
    """Informa o horário de funcionamento de uma unidade (informação pública)."""
    return {}


_BASE = (
    "Você é o assistente virtual da Prefeitura do Rio no WhatsApp. Ajude o "
    "cidadão de forma cordial. Use as ferramentas disponíveis quando apropriado."
)

# (rótulo, mensagem do cidadão) — a checagem por rótulo está no loop em main()
_CASES = [
    ("restrito", "Quero consultar minhas multas de trânsito"),
    ("público", "Qual o horário de funcionamento da prefeitura hoje?"),
]


def main() -> int:
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("SKIP: sem GEMINI_API_KEY/GOOGLE_API_KEY no env.")
        return 0

    from langchain_google_genai import ChatGoogleGenerativeAI

    system = _BASE + "\n\n" + govbr_auth_gating.MODULE_PROMPT
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0).bind_tools(
        [govbr_auth_status, govbr_auth_init, govbr_logout, consultar_multas, horario_funcionamento]
    )

    ok = True
    for label, msg in _CASES:
        try:
            resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=msg)])
        except Exception as exc:  # nunca ecoa a key
            # exit 2 = NÃO-AVALIADO (erro de rede/quota/Gemini), distinto de
            # exit 1 = gating incorreto. Operador/CI não confunde os dois.
            print(f"  [{label}] INDETERMINADO (erro ao invocar Gemini, não é falha de gating): {type(exc).__name__}: {exc}")
            return 2
        calls = [c["name"] for c in (resp.tool_calls or [])]
        if label == "restrito":
            # gateado: checa auth_status e NÃO chama o serviço restrito ainda
            # (este último também cobre a mitigação do same-turn parallel call)
            passed = "govbr_auth_status" in calls and "consultar_multas" not in calls
        else:
            passed = "govbr_auth_status" not in calls and "govbr_auth_init" not in calls
        ok = ok and passed
        print(f"  [{label}] msg={msg!r}\n    tool_calls={calls}  -> {'PASS' if passed else 'FAIL'}")

    print("PASS: orquestração gateia restrito e libera público." if ok else "FAIL: gating incorreto.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
