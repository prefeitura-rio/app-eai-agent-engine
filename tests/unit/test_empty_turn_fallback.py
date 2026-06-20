"""Testes do safety-net contra turno-vazio (no-response device-confirmado 2026-06-20).

Com um Flow card pendente, o LLM às vezes emite um AIMessage VAZIO (sem content, sem
tool_calls); o grafo encerra o turno e o Mule pula o envio
(``outbound_skipped_empty`` / ``completed_no_assistant_message``) → cidadão sem
resposta. ``ensure_non_empty_assistant_turn`` injeta um fallback SOMENTE quando o turno
não produziu nada voltado ao cidadão (sem texto E sem tool voltada ao cidadão), sem
duplicar interativo/mídia. Tools INTERNAS não contam (um vazio depois delas ainda é
no-response).
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engine.interactive_tools import (
    ensure_non_empty_assistant_turn,
    EMPTY_TURN_FALLBACK_MESSAGE,
)


def test_injects_on_empty_turn():
    """Turno bug: HumanMessage + AIMessage vazio, sem tool → injeta o fallback."""
    messages = [HumanMessage(content="quero abrir um chamado"), AIMessage(content="")]
    injected = ensure_non_empty_assistant_turn(messages)
    assert injected is True
    assert messages[-1].content == EMPTY_TURN_FALLBACK_MESSAGE
    assert messages[-1].additional_kwargs.get("synthetic_empty_turn_fallback") is True


def test_injects_after_internal_tool():
    """Tool INTERNA (google_search) + turno vazio → ainda é no-response → injeta.

    Regressão do P2 codex: o check largo "qualquer ToolMessage → pula" deixava o
    cidadão sem resposta em turnos com tool interna + AIMessage vazio."""
    messages = [
        HumanMessage(content="qual o horário?"),
        ToolMessage(content="resultado", name="google_search", tool_call_id="t0"),
        AIMessage(content=""),
    ]
    assert ensure_non_empty_assistant_turn(messages) is True
    assert messages[-1].content == EMPTY_TURN_FALLBACK_MESSAGE


def test_noop_when_text_present():
    """Já há texto pro cidadão → não injeta."""
    messages = [HumanMessage(content="oi"), AIMessage(content="Olá! 😊")]
    assert ensure_non_empty_assistant_turn(messages) is False
    assert len(messages) == 2


def test_noop_when_interactive_sent_out_of_band():
    """Interativo já enviado out-of-band (ToolMessage) → não injeta (não duplica)."""
    messages = [
        HumanMessage(content="luminária"),
        ToolMessage(
            content='{"status": "interactive_sent"}',
            name="multi_step_service",
            tool_call_id="t1",
        ),
        AIMessage(content=""),
    ]
    assert ensure_non_empty_assistant_turn(messages) is False
    assert all(
        m.additional_kwargs.get("synthetic_empty_turn_fallback") is not True
        for m in messages
        if isinstance(m, AIMessage)
    )


def test_noop_when_media_tool_ran():
    """Tool de MÍDIA (generate_audio_response, vira agentMedia no Mule) → não injeta."""
    messages = [
        HumanMessage(content="manda o áudio"),
        ToolMessage(content="ok", name="generate_audio_response", tool_call_id="t2"),
        AIMessage(content=""),
    ]
    assert ensure_non_empty_assistant_turn(messages) is False
    assert len(messages) == 3


def test_noop_on_non_list():
    """Robustez: filtered_result sem messages (None) → não estoura, não injeta."""
    assert ensure_non_empty_assistant_turn(None) is False


def test_injects_when_only_tool_call_preamble_then_empty():
    """AIMessage com preâmbulo + tool_calls NÃO é resposta final; vazio depois → injeta.

    Regressão do P2 codex round 2: content de um AIMessage que também tem tool_calls
    (preâmbulo/thinking) não pode contar como resposta final entregue."""
    messages = [
        HumanMessage(content="qual o horário?"),
        AIMessage(
            content="Deixa eu verificar...",
            tool_calls=[{"name": "google_search", "args": {}, "id": "tc1"}],
        ),
        ToolMessage(content="resultado", name="google_search", tool_call_id="tc1"),
        AIMessage(content=""),
    ]
    assert ensure_non_empty_assistant_turn(messages) is True
    assert messages[-1].content == EMPTY_TURN_FALLBACK_MESSAGE


def test_injects_when_media_tool_deferred():
    """Mídia com falha a nível de dado ({status:deferred}) → sem mídia → injeta.

    Regressão do P2 codex round 2: tool de mídia pode retornar falha de dado num
    ToolMessage normal; aí não há mídia e o fallback NÃO pode ser suprimido."""
    messages = [
        HumanMessage(content="manda o áudio"),
        ToolMessage(
            content='{"status": "deferred"}',
            name="generate_audio_response",
            tool_call_id="t3",
        ),
        AIMessage(content=""),
    ]
    assert ensure_non_empty_assistant_turn(messages) is True
    assert messages[-1].content == EMPTY_TURN_FALLBACK_MESSAGE
