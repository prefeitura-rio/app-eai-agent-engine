import ast
import json
from typing import Any, Iterable

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool


INTERACTIVE_RESPONSE_TOOL_NAMES = frozenset(
    {
        "build_whatsapp_flow_envelope",
        "send_whatsapp_buttons",
        "send_whatsapp_list",
    }
)


def mark_interactive_tools_return_direct(tools: Iterable[BaseTool]) -> list[BaseTool]:
    """Stop the ReAct loop after tools whose return is the citizen-facing message."""
    tool_list = list(tools)
    for tool in tool_list:
        if tool.name in INTERACTIVE_RESPONSE_TOOL_NAMES:
            tool.return_direct = True
    return tool_list


def is_successful_interactive_tool_message(message: object) -> bool:
    """Whether a ToolMessage is a successful citizen-facing interactive envelope."""
    return (
        isinstance(message, ToolMessage)
        and message.name in INTERACTIVE_RESPONSE_TOOL_NAMES
        and getattr(message, "status", None) != "error"
    )


def is_failed_interactive_tool_message(message: object) -> bool:
    """Whether a ToolMessage is a failed citizen-facing interactive envelope."""
    return (
        isinstance(message, ToolMessage)
        and message.name in INTERACTIVE_RESPONSE_TOOL_NAMES
        and getattr(message, "status", None) == "error"
    )


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
