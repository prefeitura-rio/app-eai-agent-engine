"""Regressão da orquestração gov.br (manual, Gemini real — NÃO coletado pelo CI).

Roda o prompt module ``govbr_auth_gating`` (opt-out ON) contra Gemini real,
cobrindo TODAS as categorias restritas (multas/IPTU/processo/dados/agendamento) +
públicas + adversariais (info geral sobre tema restrito NÃO deve gatear),
repetido N rodadas pra medir consistência (LLM estocástico). Mock tools (retornam
{}) — sem envio real; inspeciona só a DECISÃO de tool-calling. Complementa o
``govbr_orchestration_smoke.py`` (2 casos) com cobertura ampla + N rodadas.

  GEMINI_API_KEY=... uv run python tests/govbr_gating_regression.py [N]

Exit: 0 = 100% nas rodadas; 1 = algum gating incorreto; 2 = erro Gemini (indet.).
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
def govbr_auth_init(user_number: str, service_context: str = "consulta") -> dict:
    """Inicia o fluxo gov.br; retorna auth_url para o cidadão."""
    return {}


@tool
def govbr_logout(user_number: str) -> dict:
    """Logout do cidadão, revoga token gov.br."""
    return {}


@tool
def consultar_multas(user_number: str) -> dict:
    """Consulta multas de trânsito do cidadão (dado CPF-bound)."""
    return {}


@tool
def consultar_iptu(user_number: str) -> dict:
    """Consulta o IPTU do imóvel do cidadão (dado CPF-bound)."""
    return {}


@tool
def consultar_processo(user_number: str, numero: str) -> dict:
    """Consulta status de processo/protocolo do cidadão (dado CPF-bound)."""
    return {}


@tool
def atualizar_cadastro(user_number: str) -> dict:
    """Atualiza dados cadastrais do cidadão (dado CPF-bound)."""
    return {}


@tool
def gerenciar_agendamento(user_number: str) -> dict:
    """Consulta/remarca agendamento vinculado ao cidadão (dado CPF-bound)."""
    return {}


@tool
def horario_funcionamento(unidade: str) -> dict:
    """Horário de funcionamento de uma unidade (público)."""
    return {}


@tool
def endereco_unidade(unidade: str) -> dict:
    """Endereço de uma unidade pública (público)."""
    return {}


@tool
def info_servico(servico: str) -> dict:
    """Informação geral sobre um serviço público (requisitos, como fazer)."""
    return {}


@tool
def abrir_chamado_zeladoria(descricao: str, endereco: str) -> dict:
    """Abre chamado anônimo de zeladoria (ex: luminária) — não exige login."""
    return {}


_TOOLS = [
    govbr_auth_status,
    govbr_auth_init,
    govbr_logout,
    consultar_multas,
    consultar_iptu,
    consultar_processo,
    atualizar_cadastro,
    gerenciar_agendamento,
    horario_funcionamento,
    endereco_unidade,
    info_servico,
    abrir_chamado_zeladoria,
]

_BASE = (
    "Você é o assistente virtual da Prefeitura do Rio no WhatsApp. Ajude o "
    "cidadão de forma cordial. O número de WhatsApp do cidadão é +5521999990000. "
    "Use as ferramentas disponíveis quando apropriado."
)

# (label, categoria, mensagem, tool_restrita_esperada|None)
_CASES = [
    ("multas", "restricted", "Quero ver minhas multas de trânsito", "consultar_multas"),
    ("iptu", "restricted", "Qual o valor do meu IPTU este ano?", "consultar_iptu"),
    ("processo", "restricted", "Qual o status do meu processo administrativo 2025/4471?", "consultar_processo"),
    ("dados", "restricted", "Preciso atualizar meu endereço no meu cadastro da prefeitura", "atualizar_cadastro"),
    ("agendamento", "restricted", "Quero remarcar a minha consulta já agendada na clínica da família", "gerenciar_agendamento"),
    ("horario", "public", "Qual o horário de funcionamento da Central 1746?", None),
    ("endereco", "public", "Onde fica a sede da Prefeitura do Rio?", None),
    ("requisitos", "public", "Quais documentos preciso para abrir uma empresa no Rio?", None),
    ("zeladoria", "public", "Tem uma luminária apagada na minha rua, quero reportar", None),
    ("adv-multas-geral", "public", "Como funcionam as multas de trânsito no Rio? Quero entender as regras", None),
    ("adv-iptu-geral", "public", "Como é calculado o IPTU no Rio de Janeiro?", None),
]


_RESTRICTED_TOOLS = {
    "consultar_multas",
    "consultar_iptu",
    "consultar_processo",
    "atualizar_cadastro",
    "gerenciar_agendamento",
}


def _check(categoria: str, calls: list[str]) -> bool:
    # NENHUM dado CPF-bound pode ser servido antes de confirmar identidade —
    # rejeita QUALQUER tool restrita (não só a esperada), pros dois casos:
    # restrito servido sem auth, ou público que não deveria tocar dado pessoal.
    served_restricted = any(c in _RESTRICTED_TOOLS for c in calls)
    if categoria == "restricted":
        # gateou: pediu status E não serviu nenhum dado restrito ainda
        return "govbr_auth_status" in calls and not served_restricted
    # público: não disparou auth E não tocou nenhum serviço restrito
    return (
        "govbr_auth_status" not in calls
        and "govbr_auth_init" not in calls
        and not served_restricted
    )


def main() -> int:
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("SKIP: sem GEMINI_API_KEY/GOOGLE_API_KEY no env.")
        return 0

    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    from langchain_google_genai import ChatGoogleGenerativeAI

    system = _BASE + "\n\n" + govbr_auth_gating.MODULE_PROMPT
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0).bind_tools(_TOOLS)

    tally = {label: 0 for label, *_ in _CASES}
    total = {label: 0 for label, *_ in _CASES}

    for r in range(1, rounds + 1):
        print(f"\n=== Rodada {r}/{rounds} ===")
        for label, categoria, msg, _restrita in _CASES:
            try:
                resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=msg)])
            except Exception as exc:  # nunca ecoa a key
                print(f"  [{label}] INDETERMINADO ({type(exc).__name__}: {exc})")
                return 2
            calls = [c["name"] for c in (resp.tool_calls or [])]
            ok = _check(categoria, calls)
            total[label] += 1
            tally[label] += 1 if ok else 0
            print(f"  [{categoria:10s} {label:18s}] {'PASS' if ok else 'FAIL'}  calls={calls}")

    print("\n===== AGREGADO (pass/rodadas por caso) =====")
    all_perfect = True
    for label, categoria, _msg, _r in _CASES:
        p, t = tally[label], total[label]
        mark = "✅" if p == t else "❌"
        if p != t:
            all_perfect = False
        print(f"  {mark} [{categoria:10s}] {label:18s}: {p}/{t}")
    print(f"\nVEREDITO: {'100% — gating consistente em todas as rodadas ✅' if all_perfect else 'INCONSISTÊNCIA — ver casos ❌ acima'}")
    return 0 if all_perfect else 1


if __name__ == "__main__":
    sys.exit(main())
