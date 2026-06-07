from langchain_core.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from engine.custom_react_agent import create_react_agent
from engine.agent import Agent
from engine.interactive_tools import mark_interactive_tools_return_direct


@tool
def build_whatsapp_flow_envelope(flow_id: str) -> str:
    """Mock interactive Flow builder."""
    return flow_id


@tool
def send_whatsapp_buttons(body: str) -> str:
    """Mock interactive button sender."""
    return body


@tool
def google_search(query: str) -> str:
    """Mock non-interactive search."""
    return query


@tool
def send_whatsapp_list(body: str) -> list[dict[str, str]]:
    """Mock interactive list sender returning an MCP-style content block list."""
    return [{"type": "text", "text": body}]


@tool
def list_service_options() -> list[dict[str, str]]:
    """Mock non-interactive tool returning a structured list."""
    return [{"name": "luminaria"}, {"name": "poda"}]


def test_interactive_tools_return_direct_only_for_interactive_messages():
    tools = mark_interactive_tools_return_direct(
        [build_whatsapp_flow_envelope, send_whatsapp_buttons, google_search]
    )

    by_name = {tool.name: tool for tool in tools}
    assert by_name["build_whatsapp_flow_envelope"].return_direct is True
    assert by_name["send_whatsapp_buttons"].return_direct is True
    assert by_name["google_search"].return_direct is False


class _InteractiveToolCallingModel(BaseChatModel):
    calls: int = 0
    tool_calls_to_emit: list[dict] | None = None

    @property
    def _llm_type(self):
        return "fake-interactive-tool-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            tool_calls = self.tool_calls_to_emit or []
            message = AIMessage(content="", tool_calls=tool_calls)
        else:
            message = AIMessage(content="texto indevido depois do Flow")
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_interactive_return_direct_stops_react_loop_with_post_model_hook():
    tools = mark_interactive_tools_return_direct([build_whatsapp_flow_envelope])
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "build_whatsapp_flow_envelope",
                "args": {"flow_id": "4141008006029185"},
                "id": "flow-call",
                "type": "tool_call",
            }
        ]
    )

    graph = create_react_agent(
        model=model,
        tools=tools,
        post_model_hook=lambda _state, config=None: {},
    )

    result = graph.invoke({"messages": [HumanMessage(content="luminaria apagada")]})

    assert model.calls == 1
    assert isinstance(result["messages"][-1], ToolMessage)
    assert result["messages"][-1].name == "build_whatsapp_flow_envelope"


def test_interactive_return_direct_keeps_interactive_tool_message_last():
    tools = mark_interactive_tools_return_direct(
        [build_whatsapp_flow_envelope, google_search]
    )
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "build_whatsapp_flow_envelope",
                "args": {"flow_id": "4141008006029185"},
                "id": "flow-call",
                "type": "tool_call",
            },
            {
                "name": "google_search",
                "args": {"query": "luminaria"},
                "id": "search-call",
                "type": "tool_call",
            },
        ]
    )

    graph = create_react_agent(model=model, tools=tools)
    raw_result = graph.invoke({"messages": [HumanMessage(content="luminaria apagada")]})
    result = Agent._filter_current_interaction(object(), raw_result)

    assert model.calls == 1
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == [
        "google_search",
        "build_whatsapp_flow_envelope",
    ]
    assert result["messages"][-1].name == "build_whatsapp_flow_envelope"


def test_interactive_return_direct_normalizes_tool_message_content():
    tools = mark_interactive_tools_return_direct([send_whatsapp_list])
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "send_whatsapp_list",
                "args": {"body": "Escolha uma opção"},
                "id": "list-call",
                "type": "tool_call",
            }
        ]
    )

    graph = create_react_agent(model=model, tools=tools)
    result = graph.invoke({"messages": [HumanMessage(content="opções")]})

    last = result["messages"][-1]
    assert isinstance(last, ToolMessage)
    assert last.name == "send_whatsapp_list"
    assert last.content == {"type": "text", "text": "Escolha uma opção"}
    assert "timestamp" in last.additional_kwargs


def test_non_interactive_tool_list_content_is_not_normalized_in_tool_node():
    tools = [list_service_options]
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "list_service_options",
                "args": {},
                "id": "options-call",
                "type": "tool_call",
            }
        ]
    )

    graph = create_react_agent(model=model, tools=tools)
    result = graph.invoke({"messages": [HumanMessage(content="opções")]})

    tool_message = next(
        m for m in result["messages"] if isinstance(m, ToolMessage)
    )
    assert tool_message.content == '[{"name": "luminaria"}, {"name": "poda"}]'
    assert "timestamp" in tool_message.additional_kwargs


def test_interactive_return_direct_does_not_stop_on_tool_error():
    tools = mark_interactive_tools_return_direct([build_whatsapp_flow_envelope])
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "build_whatsapp_flow_envelope",
                "args": {},
                "id": "flow-call",
                "type": "tool_call",
            }
        ]
    )

    graph = create_react_agent(model=model, tools=tools)
    result = graph.invoke({"messages": [HumanMessage(content="luminaria apagada")]})

    assert model.calls == 2
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1].content == "texto indevido depois do Flow"

    filtered_result = Agent._filter_current_interaction(object(), result)
    assert isinstance(filtered_result["messages"][-1], AIMessage)
    assert filtered_result["messages"][-1].content == "texto indevido depois do Flow"


def test_interactive_reorder_does_not_cross_recovery_ai_message():
    tools = mark_interactive_tools_return_direct(
        [build_whatsapp_flow_envelope, send_whatsapp_buttons]
    )
    model = _InteractiveToolCallingModel(
        tool_calls_to_emit=[
            {
                "name": "build_whatsapp_flow_envelope",
                "args": {},
                "id": "flow-call",
                "type": "tool_call",
            },
            {
                "name": "send_whatsapp_buttons",
                "args": {"body": "Quer continuar?"},
                "id": "buttons-call",
                "type": "tool_call",
            },
        ]
    )

    graph = create_react_agent(model=model, tools=tools)
    raw_result = graph.invoke({"messages": [HumanMessage(content="luminaria apagada")]})
    filtered_result = Agent._filter_current_interaction(object(), raw_result)

    assert model.calls == 2
    assert isinstance(filtered_result["messages"][-1], AIMessage)
    assert filtered_result["messages"][-1].content == "texto indevido depois do Flow"


def test_interactive_recovery_ai_wins_over_late_parallel_success():
    result = {
        "messages": [
            HumanMessage(content="luminaria apagada"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_whatsapp_flow_envelope",
                        "args": {},
                        "id": "flow-call",
                        "type": "tool_call",
                    },
                    {
                        "name": "send_whatsapp_buttons",
                        "args": {"body": "Quer continuar?"},
                        "id": "buttons-call",
                        "type": "tool_call",
                    },
                ],
            ),
            ToolMessage(
                content="erro de validação",
                name="build_whatsapp_flow_envelope",
                status="error",
                tool_call_id="flow-call",
            ),
            AIMessage(content="Pode tentar enviar novamente?"),
            ToolMessage(
                content="buttons:ok",
                name="send_whatsapp_buttons",
                tool_call_id="buttons-call",
            ),
        ]
    }

    filtered_result = Agent._filter_current_interaction(object(), result)

    assert isinstance(filtered_result["messages"][-1], AIMessage)
    assert filtered_result["messages"][-1].content == "Pode tentar enviar novamente?"


def test_interactive_retry_tool_after_error_wins_over_ai_with_tool_call():
    result = {
        "messages": [
            HumanMessage(content="luminaria apagada"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_whatsapp_flow_envelope",
                        "args": {},
                        "id": "bad-flow-call",
                        "type": "tool_call",
                    },
                ],
            ),
            ToolMessage(
                content="erro de validação",
                name="build_whatsapp_flow_envelope",
                status="error",
                tool_call_id="bad-flow-call",
            ),
            AIMessage(
                content="Vou tentar novamente.",
                tool_calls=[
                    {
                        "name": "build_whatsapp_flow_envelope",
                        "args": {"flow_id": "4141008006029185"},
                        "id": "good-flow-call",
                        "type": "tool_call",
                    },
                ],
            ),
            ToolMessage(
                content={"flow": "ok"},
                name="build_whatsapp_flow_envelope",
                tool_call_id="good-flow-call",
            ),
        ]
    }

    filtered_result = Agent._filter_current_interaction(object(), result)

    assert isinstance(filtered_result["messages"][-1], ToolMessage)
    assert filtered_result["messages"][-1].name == "build_whatsapp_flow_envelope"
