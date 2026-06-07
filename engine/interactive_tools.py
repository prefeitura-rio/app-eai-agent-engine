from typing import Iterable

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
