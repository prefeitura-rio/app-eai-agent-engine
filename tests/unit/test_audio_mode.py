"""Testes do modo áudio contínuo (engine/audio_mode.py)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from engine.audio_mode import (
    AUDIO_MODE_DIRECTIVE,
    audio_mode_directive_message,
    derive_audio_mode,
    inject_audio_directive,
)


def _h(text):
    return HumanMessage(content=text)


# --------------------------------------------------------------------------- #
# derive_audio_mode — ON
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "fica em áudio sempre",
        "responde sempre em áudio",
        "sempre em audio",  # sem acento
        "pode continuar falando",
        "continua no áudio por favor",
        "quero tudo em áudio",
        "só áudio daqui pra frente",
        "não precisa mais escrever, pode falar",
        "para de escrever, manda só falado",
        "me responde sempre falando",
    ],
)
def test_on_phrases(text):
    assert derive_audio_mode([_h(text)]) is True


# --------------------------------------------------------------------------- #
# derive_audio_mode — OFF / não-contínuo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "volta pra texto",
        "volta a escrever",
        "para de áudio",
        "desliga o audio",
        "chega de áudio",
        "sem áudio agora",
        "não precisa de áudio",
        "prefiro ler",
        "manda por texto",
        "responde escrevendo",
        "pode escrever",
        "escreve aí",
    ],
)
def test_off_phrases(text):
    assert derive_audio_mode([_h(text)]) is False


@pytest.mark.parametrize(
    "text",
    [
        "me responda com áudio",  # pedido pontual, NÃO contínuo
        "manda um áudio dessa resposta",
        "como abro um chamado de luminária?",
        "bom dia",
        "",
    ],
)
def test_one_shot_or_neutral_is_off(text):
    """Pedido pontual ou sem diretiva → texto (default)."""
    assert derive_audio_mode([_h(text)]) is False


def test_empty_history_is_off():
    assert derive_audio_mode([]) is False


# --------------------------------------------------------------------------- #
# Mais recente vence
# --------------------------------------------------------------------------- #
def test_newest_directive_wins_off_after_on():
    history = [_h("fica sempre em áudio"), _h("agora volta pra texto")]
    assert derive_audio_mode(history) is False


def test_newest_directive_wins_on_after_off():
    history = [_h("volta pra texto"), _h("não, fica sempre em áudio")]
    assert derive_audio_mode(history) is True


def test_intervening_neutral_messages_dont_reset():
    history = [
        _h("fica sempre em áudio"),
        _h("qual o horário do posto?"),
        _h("e a vacina da gripe?"),
    ]
    assert derive_audio_mode(history) is True


def test_content_request_with_ler_does_not_disable_audio():
    """'quero ler o edital' é pedido de conteúdo, não troca de formato — não desliga áudio."""
    history = [_h("fica sempre em áudio"), _h("quero ler o edital de licitação")]
    assert derive_audio_mode(history) is True


# --------------------------------------------------------------------------- #
# Robustez: ignora mensagens não-humanas
# --------------------------------------------------------------------------- #
def test_ignores_non_human_messages():
    history = [
        _h("fica sempre em áudio"),
        AIMessage(content="Claro, vou responder em áudio sempre."),
        SystemMessage(content="MODO ÁUDIO CONTÍNUO ATIVO ..."),
    ]
    # Só a HumanMessage conta; AIMessage/SystemMessage com "áudio" não viram OFF/ON.
    assert derive_audio_mode(history) is True


def test_list_content_blocks_are_read():
    msg = HumanMessage(content=[{"type": "text", "text": "fica sempre em áudio"}])
    assert derive_audio_mode([msg]) is True


# --------------------------------------------------------------------------- #
# Diretiva
# --------------------------------------------------------------------------- #
def test_directive_is_system_message():
    msg = audio_mode_directive_message()
    assert isinstance(msg, SystemMessage)
    assert "MODO ÁUDIO CONTÍNUO ATIVO" in msg.content
    assert msg.content == AUDIO_MODE_DIRECTIVE


# --------------------------------------------------------------------------- #
# inject_audio_directive
# --------------------------------------------------------------------------- #
def test_inject_appends_when_on_with_llm_input_messages():
    state = {"messages": [_h("fica sempre em áudio")]}
    base = [_h("fica sempre em áudio")]
    final_state = {"llm_input_messages": list(base), "extra": 1}

    out = inject_audio_directive(state, final_state)

    assert out["extra"] == 1
    assert len(out["llm_input_messages"]) == len(base) + 1
    assert isinstance(out["llm_input_messages"][-1], SystemMessage)
    assert "MODO ÁUDIO CONTÍNUO ATIVO" in out["llm_input_messages"][-1].content


def test_inject_creates_llm_input_from_messages_when_absent():
    state = {"messages": [_h("não precisa mais escrever")]}
    final_state = {"messages": [_h("não precisa mais escrever")]}

    out = inject_audio_directive(state, final_state)

    assert "llm_input_messages" in out
    assert isinstance(out["llm_input_messages"][-1], SystemMessage)
    # messages (canal persistido) não ganha a diretiva
    assert all(
        not isinstance(m, SystemMessage)
        or "MODO ÁUDIO CONTÍNUO" not in getattr(m, "content", "")
        for m in out["messages"]
    )


def test_inject_noop_when_off():
    state = {"messages": [_h("volta pra texto")]}
    final_state = {"llm_input_messages": [_h("volta pra texto")]}

    out = inject_audio_directive(state, final_state)

    assert out is final_state  # inalterado
    assert len(out["llm_input_messages"]) == 1
