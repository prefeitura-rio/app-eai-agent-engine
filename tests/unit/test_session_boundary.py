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


# --------------------------------------------------------------------------- #
# Handshake de encerramento (2026-06-03): "sair" → bot pergunta "quer
# cancelar?" → "sim". A resposta NÃO pode ser truncada pra fora do contexto.
# --------------------------------------------------------------------------- #
def test_close_confirmation_answer_not_treated_as_new_session():
    """'sair' → bot pergunta confirmação → 'sim': o 'sim' responde o handshake,
    não inicia sessão nova. current_session_messages devolve TUDO (sem truncar)
    pra o LLM entender que 'sim' = confirmar o encerramento."""
    msgs = [
        _h("oi, tenho uma luminária apagada"),
        _a("Vou abrir o chamado. [Flow]"),
        _h("sair"),  # close intent
        _a("Você quer cancelar a solicitação de reparo de luminária? 🤔"),  # pergunta
        _h("Sim"),  # resposta ao handshake — NÃO é sessão nova
    ]
    assert current_session_messages(msgs) == msgs


def test_apply_reset_noop_during_close_confirmation():
    """apply_session_reset não trunca enquanto o handshake de cancelamento
    está em curso (senão o 'sim' vira órfão → 'Sim, mas sim o quê?')."""
    full = [
        _h("quero abrir chamado de luminária"),
        _a("Confirma os dados no formulário [Flow]"),
        _h("sair"),
        _a("Quer cancelar a solicitação que estamos abrindo?"),
        _h("Sim"),
    ]
    state = {"messages": full}
    final_state = {"llm_input_messages": list(full)}
    out = apply_session_reset(state, final_state)
    # noop: o handshake inteiro é preservado (o bot precisa do contexto p/ fechar)
    assert out is final_state


def test_reset_after_close_confirmation_resolved():
    """Depois que o cancelamento foi confirmado e o bot se despediu, a PRÓXIMA
    mensagem (turno do bot anterior NÃO é pergunta) inicia sessão nova."""
    msgs = [
        _h("quero abrir chamado de luminária"),
        _a("Confirma no formulário [Flow]"),
        _h("sair"),
        _a("Quer cancelar a solicitação?"),  # pergunta
        _h("Sim"),  # resolve o handshake
        _a("Cancelado. Qualquer coisa é só chamar 👋"),  # despedida (sem '?')
        _h("na verdade, quero pagar o IPTU"),  # sessão nova começa AQUI
    ]
    out = current_session_messages(msgs)
    assert out == msgs[6:]
    assert out[0].content.startswith("na verdade")


def test_new_topic_after_courtesy_question_still_resets():
    """Guard NÃO engole pedido novo: se o bot fechou com pergunta de cortesia
    ('posso ajudar em mais algo?') e o cidadão traz tópico NOVO (fora do set de
    respostas de handshake), a sessão reseta normalmente (sem vazar contexto)."""
    msgs = [
        _h("responde sempre em áudio"),
        _a("ok, áudio ligado"),
        _h("tchau"),  # close
        _a("Prontinho! Posso ajudar em mais alguma coisa? 😊"),  # cortesia c/ '?'
        _h("quero pagar o IPTU"),  # tópico NOVO — não é resposta de handshake
    ]
    out = current_session_messages(msgs)
    assert out == msgs[4:]
    assert out[0].content == "quero pagar o IPTU"
    # áudio reseta (contexto não vazou)
    assert derive_audio_mode(out) is False


def test_no_infinite_context_leak_with_repeated_questions():
    """Mesmo se vários turnos do bot terminam em '?', um pedido substantivo
    (fora do set de handshake) reseta — sem vazamento infinito."""
    msgs = [
        _h("oi"),
        _a("olá, como ajudo?"),
        _h("encerrar atendimento"),  # close
        _a("Quer mesmo encerrar?"),
        _h("quero abrir um chamado de poda de árvore na minha rua"),  # novo
    ]
    out = current_session_messages(msgs)
    assert out == msgs[4:]


def test_ends_with_question_robustness():
    from engine.session_boundary import _ends_with_question

    assert _ends_with_question("Quer cancelar?") is True
    assert _ends_with_question("Quer cancelar? 🤔") is True
    assert _ends_with_question("Quer mesmo cancelar?!") is True
    assert _ends_with_question("Quer cancelar?...") is True
    assert _ends_with_question("Prontinho! Até mais 👋") is False
    assert _ends_with_question("Vou aguardar.") is False
    assert _ends_with_question("") is False


@pytest.mark.parametrize(
    "answer",
    ["Sim", "Sim.", "Sim!", "Sim 👍", "  sim  ", "claro!", "Pode cancelar.", "👍 sim"],
)
def test_close_answer_with_punctuation_emoji_not_orphaned(answer):
    """Formas comuns no WhatsApp ('Sim.', 'Sim!', 'Sim 👍') respondendo à
    confirmação NÃO podem orfanar — a sessão não reseta no meio do handshake."""
    msgs = [
        _h("quero abrir chamado de luminária"),
        _a("Confirma no formulário [Flow]"),
        _h("sair"),
        _a("Quer cancelar a solicitação que estamos abrindo?"),
        _h(answer),
    ]
    # handshake preservado (não trunca pro 'answer' órfão)
    assert current_session_messages(msgs) == msgs
