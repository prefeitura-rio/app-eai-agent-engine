import ast
import json
from typing import Any, Iterable

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool


INTERACTIVE_RESPONSE_TOOL_NAMES = frozenset({"build_whatsapp_flow_envelope"})

# Tools interativas NÃO-Flow (botões/lista): o content delas É a estrutura
# interativa voltada ao cidadão (lista de blocos), então NÃO deve ser normalizada
# para o primeiro item. As tools NÃO-interativas (multi_step_service,
# google_search, …), ao contrário, vêm do adapter MCP como `["texto"]` e precisam
# da normalização content[0] (fix 4f65686).
NON_FLOW_INTERACTIVE_TOOL_NAMES = frozenset(
    {"send_whatsapp_buttons", "send_whatsapp_list"}
)
ALL_INTERACTIVE_TOOL_NAMES = (
    INTERACTIVE_RESPONSE_TOOL_NAMES | NON_FLOW_INTERACTIVE_TOOL_NAMES
)


def mark_interactive_tools_return_direct(tools: Iterable[BaseTool]) -> list[BaseTool]:
    """Stop the ReAct loop after tools whose return is the citizen-facing message.

    Cobre Flow (``build_whatsapp_flow_envelope``) E os interativos não-Flow
    (``send_whatsapp_buttons`` / ``send_whatsapp_list``): o envelope que essas tools
    retornam JÁ É a mensagem entregue ao cidadão, então o turno encerra ali. Sem o
    ``return_direct``, o LLM podia escrever texto depois — e esse texto descartaria o
    interativo no caminho engine→gateway→Mule (Feature 1: botões/listas proativos).
    """
    tool_list = list(tools)
    for tool in tool_list:
        if tool.name in ALL_INTERACTIVE_TOOL_NAMES:
            tool.return_direct = True
    return tool_list


def is_successful_interactive_tool_message(message: object) -> bool:
    """Whether a ToolMessage is a successful citizen-facing interactive envelope.

    Inclui Flow + botões/lista (``ALL_INTERACTIVE_TOOL_NAMES``): todos são respostas
    interativas voltadas ao cidadão que encerram o turno (preview p/ eval +
    reposicionamento como última mensagem)."""
    return (
        isinstance(message, ToolMessage)
        and message.name in ALL_INTERACTIVE_TOOL_NAMES
        and getattr(message, "status", None) != "error"
    )


def is_failed_interactive_tool_message(message: object) -> bool:
    """Whether a ToolMessage is a failed citizen-facing interactive envelope."""
    return (
        isinstance(message, ToolMessage)
        and message.name in ALL_INTERACTIVE_TOOL_NAMES
        and getattr(message, "status", None) == "error"
    )


def _tool_message_text(message: ToolMessage) -> str:
    """Extrai o texto JSON do ``content`` de um ToolMessage de forma robusta:
    aceita ``str``, lista de blocos ``[{'type':'text','text':...}]`` (formato do
    adapter MCP) ou ``dict``."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("text", "") or "")
        return str(first)
    if isinstance(content, dict):
        return str(content.get("text", "") or "")
    return str(content) if content is not None else ""


def is_mss_interactive_sent_message(message: object) -> bool:
    """Whether a ``multi_step_service`` ToolMessage signals an interactive já enviado
    out-of-band (``status: interactive_sent``) — turno deve encerrar.

    O ``multi_step_service`` NÃO está em ``ALL_INTERACTIVE_TOOL_NAMES`` (é multi-uso:
    nem todo retorno é terminal), então não pode ser ``return_direct`` sempre. Mas
    quando o gate ``ENABLE_INTERACTIVE_CONFIRM`` faz o MCP enviar os botões DIRETO pro
    cidadão, o retorno traz ``status: interactive_sent`` + instrução "não escreva". Aí
    o turno DEVE encerrar (a mensagem ao cidadão já saiu): sem isso o LLM re-chama o
    workflow e/ou escreve texto, gerando confirmação duplicada (bug 2026-06-19)."""
    if not isinstance(message, ToolMessage) or message.name != "multi_step_service":
        return False
    if getattr(message, "status", None) == "error":
        return False
    text = _tool_message_text(message)
    if "interactive_sent" not in text:
        return False
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return False
    return isinstance(data, dict) and data.get("status") == "interactive_sent"


# Tools cujo RETORNO já É a mensagem voltada ao cidadão e o Mule vira ``agentMedia``
# (webhook-flow.xml: canonicalToolReturn {send_whatsapp_media, build_whatsapp_flow_envelope,
# send_whatsapp_buttons, send_whatsapp_list} + audioTR generate_audio_response). As
# interativas Flow/botões/lista já estão em ALL_INTERACTIVE_TOOL_NAMES; aqui ficam as
# de mídia pura. Usado pelo guard de turno-vazio pra NÃO injetar fallback quando a
# saída ao cidadão já saiu por uma dessas (evitaria duplicar/descartar).
MEDIA_RETURN_TOOL_NAMES = frozenset({"send_whatsapp_media", "generate_audio_response"})


def _media_tool_succeeded(message: ToolMessage) -> bool:
    """Mídia realmente disponível? Tools de mídia podem retornar falha a nível de DADO
    (``{"status":"error"/"deferred"/"failed"}``) num ToolMessage normal — aí não há
    mídia pro cidadão e o fallback NÃO deve ser suprimido."""
    text = _tool_message_text(message)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return True  # não-JSON: conservador (assume saída; não injeta por cima de mídia)
    if isinstance(data, dict):
        return str(data.get("status", "")).lower() not in ("error", "deferred", "failed")
    return True


def _is_citizen_facing_tool_message(message: object) -> bool:
    """ToolMessage cujo retorno é a mensagem ao cidadão: interativo (Flow/botões/lista
    via return_direct), ``interactive_sent`` out-of-band, ou mídia (áudio/imagem/…)
    de SUCESSO. Tools INTERNAS (google_search, validate_address, multi_step_service
    não-terminal) NÃO contam — após elas, um turno vazio AINDA é no-response e merece
    o fallback."""
    if is_successful_interactive_tool_message(message):
        return True
    if is_mss_interactive_sent_message(message):
        return True
    return (
        isinstance(message, ToolMessage)
        and getattr(message, "status", None) != "error"
        and message.name in MEDIA_RETURN_TOOL_NAMES
        and _media_tool_succeeded(message)
    )


# Fallback p/ turno bem-sucedido mas SEM nada voltado ao cidadão (ver
# ensure_non_empty_assistant_turn). Genérico de propósito: o turno-vazio pode
# ocorrer em qualquer contexto, não só luminária.
EMPTY_TURN_FALLBACK_MESSAGE = (
    "Desculpe, não consegui entender sua última mensagem. 😕 "
    "Pode reformular ou me dizer de outro jeito o que você precisa?"
)


def _ai_message_has_visible_text(message: object) -> bool:
    """AIMessage com TEXTO final voltado ao cidadão: SEM tool_calls (preâmbulo de tool
    não é resposta final) e com texto de verdade (str não-vazia ou bloco ``type:text``
    — exclui blocos de thinking quando include_thoughts=True)."""
    if not isinstance(message, AIMessage) or getattr(message, "tool_calls", None):
        return False
    content = message.content
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str) and block.strip():
                return True
            if (
                isinstance(block, dict)
                and block.get("type", "text") == "text"
                and str(block.get("text", "")).strip()
            ):
                return True
    return False


def ensure_non_empty_assistant_turn(messages: list) -> bool:
    """Garante que um turno bem-sucedido NUNCA termine sem nada pro cidadão.

    Bug confirmado (device-test 2026-06-20): com um Flow card pendente, o LLM às
    vezes emite um AIMessage VAZIO (sem content, sem tool_calls) e o grafo encerra o
    turno — o Mule então pula o envio (``outbound_skipped_empty`` /
    ``completed_no_assistant_message``) e o cidadão fica sem resposta. A rede de
    segurança do #89 só cobre EXCEÇÃO; sucesso-vazio passava batido.

    Injeta um fallback SOMENTE quando o turno não produziu NADA voltado ao cidadão:
    nenhum texto de assistente E nenhuma tool VOLTADA AO CIDADÃO (interativo via
    return_direct, ``interactive_sent`` out-of-band, ou mídia). Tools internas
    (busca, geocode, multi_step_service não-terminal) NÃO contam — um turno vazio
    depois delas ainda é no-response. NÃO injeta quando há saída ao cidadão (evita
    duplicar/descartar). Espelha o discriminador de skip do Mule (sem texto + sem
    interactive + sem mídia). Roda só no RESULTADO FINAL de ``Agent.query`` /
    ``async_query`` (NÃO em chunks de streaming, que podem ser estados intermediários
    só com o HumanMessage), na cópia já filtrada (não polui o checkpoint).

    Retorna True se injetou o fallback.
    """
    if not isinstance(messages, list):
        return False
    if any(_ai_message_has_visible_text(message) for message in messages):
        return False  # já há texto final pro cidadão (não conta preâmbulo de tool/thinking)
    if any(_is_citizen_facing_tool_message(message) for message in messages):
        return False  # interativo / mídia / out-of-band já é a saída ao cidadão
    messages.append(
        AIMessage(
            content=EMPTY_TURN_FALLBACK_MESSAGE,
            additional_kwargs={"synthetic_empty_turn_fallback": True},
        )
    )
    return True


def put_recovery_ai_after_interactive_tool_error(messages: list) -> bool:
    """Prefer the model recovery text after a failed interactive tool call."""
    saw_failed_interactive = False
    recovery_ai_index = None
    for index, message in enumerate(messages):
        if is_failed_interactive_tool_message(message):
            saw_failed_interactive = True
            continue
        if (
            saw_failed_interactive
            and isinstance(message, AIMessage)
            and message.content
            and not message.tool_calls
        ):
            recovery_ai_index = index

    if recovery_ai_index is None:
        return False

    recovery_ai_message = messages[recovery_ai_index]
    messages[:] = (
        messages[:recovery_ai_index]
        + messages[recovery_ai_index + 1 :]
        + [recovery_ai_message]
    )
    return True


def put_interactive_tool_messages_last(messages: list) -> list:
    """Keep a successful interactive envelope as the last message in mixed tool turns."""
    trailing_start = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if not isinstance(messages[index], ToolMessage):
            break
        trailing_start = index
    if trailing_start == len(messages):
        return messages

    trailing_tool_messages = messages[trailing_start:]
    interactive = [
        message
        for message in trailing_tool_messages
        if is_successful_interactive_tool_message(message)
    ]
    if not interactive:
        return messages

    interactive_ids = {id(message) for message in interactive}
    messages[:] = messages[:trailing_start] + [
        message
        for message in trailing_tool_messages
        if id(message) not in interactive_ids
    ] + interactive
    return messages


def add_interactive_tool_preview_message(messages: list) -> bool:
    """Expose a text preview for evaluators while keeping the interactive last.

    ``return_direct`` makes the successful ToolMessage the final citizen-facing
    payload. The gateway/eval history, however, also expects an
    ``assistant_message`` for textual scoring and operator inspection. Add the
    preview only to the already-filtered response returned by ``Agent.query``;
    callers invoke this after graph execution, so persisted LangGraph history is
    not mutated.
    """
    if any(
        isinstance(message, AIMessage)
        and message.content
        and not getattr(message, "tool_calls", None)
        for message in messages
    ):
        return False

    tool_index = _last_successful_interactive_tool_index(messages)
    if tool_index is None:
        return False

    tool_message = messages[tool_index]
    preview = _preview_text_for_interactive_tool(messages, tool_message)
    if not preview:
        return False

    messages.insert(
        tool_index,
        AIMessage(
            content=preview,
            additional_kwargs={"synthetic_interactive_preview": True},
        ),
    )
    return True


def _last_successful_interactive_tool_index(messages: list) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if is_successful_interactive_tool_message(messages[index]):
            return index
    return None


def _preview_text_for_interactive_tool(
    messages: list,
    tool_message: ToolMessage,
) -> str:
    args = _tool_call_args_for_message(messages, tool_message)
    if args:
        preview = _preview_text_from_tool_args(tool_message.name or "", args)
        if preview:
            return preview

    return _preview_text_from_tool_content(tool_message.content)


def _preview_text_from_tool_args(tool_name: str, args: dict) -> str:
    body = _first_text_arg(args, ("body", "text", "message", "title"))
    if tool_name == "send_whatsapp_buttons":
        return _join_preview_parts(body, _button_option_lines(args.get("buttons")))
    if tool_name == "send_whatsapp_list":
        return _join_preview_parts(body, _list_option_lines(args.get("sections")))
    return body


def _first_text_arg(args: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _join_preview_parts(body: str, option_lines: list[str]) -> str:
    if not option_lines:
        return body
    options_text = "Opções disponíveis:\n" + "\n".join(option_lines)
    return f"{body}\n\n{options_text}" if body else options_text


def _button_option_lines(buttons: Any) -> list[str]:
    if not isinstance(buttons, list):
        return []
    lines = []
    for button in buttons:
        if not isinstance(button, dict):
            continue
        title = button.get("title")
        if isinstance(title, str) and title.strip():
            lines.append(f"- {title.strip()}")
    return lines


def _list_option_lines(sections: Any) -> list[str]:
    if not isinstance(sections, list):
        return []
    lines = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_title = section.get("title")
        if isinstance(section_title, str) and section_title.strip():
            lines.append(f"{section_title.strip()}:")
        rows = section.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            description = row.get("description")
            line = f"- {title.strip()}"
            if isinstance(description, str) and description.strip():
                line += f": {description.strip()}"
            lines.append(line)
    return lines


def _tool_call_args_for_message(messages: list, tool_message: ToolMessage) -> dict:
    tool_call_id = getattr(tool_message, "tool_call_id", None)
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("id") == tool_call_id:
                args = call.get("args") or {}
                return args if isinstance(args, dict) else {}
    return {}


def _preview_text_from_tool_content(content: Any) -> str:
    content = _decode_possible_json(content)
    if isinstance(content, list) and content:
        return _preview_text_from_tool_content(content[0])
    if isinstance(content, dict):
        for key in ("body", "text", "message", "title"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                nested = _decode_possible_json(value)
                if nested is not value:
                    nested_preview = _preview_text_from_tool_content(nested)
                    if nested_preview:
                        return nested_preview
                return value.strip()
        interactive_body = (
            content.get("interactive", {})
            .get("body", {})
            .get("text")
            if isinstance(content.get("interactive"), dict)
            else None
        )
        if isinstance(interactive_body, str) and interactive_body.strip():
            return interactive_body.strip()
    if isinstance(content, str) and content.strip() and not content.strip().startswith("{"):
        return content.strip()
    return ""


def _decode_possible_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return value
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        try:
            return ast.literal_eval(stripped)
        except (SyntaxError, ValueError, TypeError):
            return value
