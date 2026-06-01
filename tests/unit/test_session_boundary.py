"""Testes do boundary de sessão (engine/session_boundary.py)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from engine.audio_mode import derive_audio_mode
from engine.session_boundary import (
    apply_session_reset,
    current_session_messages,
    detect_close_intent,
)


def _h(text):
    return HumanMessage(content=text)


def _a(text="ok"):
    return AIMessage(content=text)


# --------------------------------------------------------------------------- #
# detect_close_intent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "tchau",
        "obrigado, tchau!",
        "era só isso",
        "era só isso mesmo, valeu",
        "pode encerrar",
        "quero encerrar o atendimento",
        "encerrar atendimento",
        "finalizar o atendimento",
        "valeu, até mais",
        "até logo",
        "não preciso de mais nada",
        "não preciso de mais ajuda",
        # "sair" como fim de atendimento (bug do teste do Bruno 2026-06-01)
        "sair",
        "quero sair",
        # "parar/cancelar atendimento|conversa" explícito
        "cancelar atendimento",
        "parar atendimento",
        "pode cancelar a conversa",
    ],
)
def test_close_intent_detected(text):
    assert detect_close_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "obrigado",  # gratidão pura não encerra
        "valeu",
        "qual o horário do posto?",
        "quero abrir um chamado de luminária",
        "me responde sempre em áudio",
        "quero ler o edital",
        "",
        # "encerrar <serviço>" é PEDIDO, não fim de sessão (não pode truncar contexto)
        "quero encerrar minha conta de luz",
        "vou encerrar minha matrícula na escola",
        "quero encerrar o contrato de aluguel",
        "preciso encerrar meu MEI",
        "como faço pra encerrar minha inscrição?",
        "quero encerrar o parcelamento da dívida",
        # gratidão com objeto pendente não encerra
        "não preciso de mais nada além do boleto",
        # "sair <serviço>" é PEDIDO, não fim de sessão
        "sair da conta de luz",
        "quero sair do cadastro",
        "quero sair da fila de espera",
        # "parar/cancelar áudio" é comando de áudio (audio_mode), NÃO fim de sessão
        "parar o áudio",
        "cancela o áudio",
        # "cancelar <serviço>" é pedido, não fim de sessão
        "cancelar o chamado",
    ],
)
def test_close_intent_not_detected(text):
    assert detect_close_intent(text) is False


def test_service_request_with_encerrar_does_not_truncate_context():
    """'quero encerrar minha conta' no meio do atendimento NÃO reseta a sessão."""
    msgs = [
        _h("quero encerrar minha conta de luz"),
        _a("Claro, me passa o número da instalação"),
        _h("é a instalação 12345"),
    ]
    # nenhum encerramento detectado → contexto inteiro preservado
    assert current_session_messages(msgs) == msgs


# --------------------------------------------------------------------------- #
# current_session_messages
# --------------------------------------------------------------------------- #
def test_no_close_returns_full():
    msgs = [_h("oi"), _a("olá"), _h("qual o horário?")]
    assert current_session_messages(msgs) == msgs


def test_close_as_latest_turn_returns_full():
    # despedida é a última mensagem do cidadão → ainda não resetou (goodbye contextual)
    msgs = [_h("oi"), _a("olá"), _h("pode encerrar")]
    assert current_session_messages(msgs) == msgs


def test_reset_starts_at_first_human_after_close():
    msgs = [
        _h("oi"),
        _a("olá"),
        _h("pode encerrar"),  # close
        _a("Prontinho! Até mais 👋"),  # goodbye
        _h("na verdade, qual o horário do posto?"),  # nova sessão começa aqui
        _a("é das 7h às 17h"),
    ]
    out = current_session_messages(msgs)
    assert out == msgs[4:]
    assert out[0].content.startswith("na verdade")


def test_most_recent_completed_close_wins():
    msgs = [
        _h("tchau"),
        _a("até mais"),
        _h("oi de novo"),  # sessão 2
        _a("olá"),
        _h("era só isso"),  # close 2
        _a("valeu!"),
        _h("opa, mais uma coisa"),  # sessão 3 começa aqui
    ]
    out = current_session_messages(msgs)
    assert out == msgs[6:]


def test_empty():
    assert current_session_messages([]) == []


# --------------------------------------------------------------------------- #
# apply_session_reset
# --------------------------------------------------------------------------- #
def test_apply_reset_noop_without_close():
    state = {"messages": [_h("oi"), _a("olá"), _h("horário?")]}
    final_state = {"llm_input_messages": list(state["messages"])}
    out = apply_session_reset(state, final_state)
    assert out is final_state


def test_apply_reset_truncates_to_current_session_keeping_system():
    full = [
        _h("fica sempre em áudio"),
        _a("ok, áudio"),
        _h("pode encerrar"),
        _a("até mais 👋"),
        _h("qual o horário do posto?"),  # nova sessão
    ]
    state = {"messages": full}
    mem = SystemMessage(content="[memória de longo prazo] cidadão chama-se Maria")
    final_state = {"llm_input_messages": [mem, *full]}

    out = apply_session_reset(state, final_state)
    llm = out["llm_input_messages"]
    # memória preservada
    assert llm[0] is mem
    # só a mensagem da sessão nova (sem o histórico pré-encerramento)
    conv = [m for m in llm if not isinstance(m, SystemMessage)]
    assert len(conv) == 1
    assert conv[0].content == "qual o horário do posto?"
    # messages (persistido) intocado
    assert state["messages"] == full


# --------------------------------------------------------------------------- #
# Integração com audio_mode: áudio reseta após encerramento
# --------------------------------------------------------------------------- #
def test_audio_mode_resets_after_close():
    # cidadão ligou áudio contínuo, encerrou, e mandou nova mensagem → áudio OFF
    full = [
        _h("responde sempre em áudio"),
        _a("ok"),
        _h("pode encerrar"),
        _a("até mais"),
        _h("qual o horário do posto?"),
    ]
    # derive sobre o histórico completo ainda veria o "sempre em áudio"
    assert derive_audio_mode(full) is True
    # mas sobre a sessão atual (pós-close) → OFF
    assert derive_audio_mode(current_session_messages(full)) is False


def test_audio_mode_persists_within_same_session():
    # sem encerramento, áudio contínuo persiste
    full = [
        _h("responde sempre em áudio"),
        _a("ok"),
        _h("qual o horário do posto?"),
    ]
    assert derive_audio_mode(current_session_messages(full)) is True
