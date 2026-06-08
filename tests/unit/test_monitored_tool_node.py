"""Testes do MonitoredToolNode — normalização de content das ToolMessages.

Cobre o B1 (regressão silenciosa do fix 4f65686): com o nó de tools rodando
ANTES do pre_model_hook, `_postprocess_tool_messages` seta o timestamp em toda
ToolMessage; isso faz o `_add_timestamp_to_tool_messages` (agent.py) pular a
própria normalização de `content[0]`. Restringir a normalização daqui só ao Flow
deixava as tools NÃO-interativas (multi_step_service, google_search, …) — que o
adapter MCP entrega como `["texto"]` (response_format=content_and_artifact) — de
volta com content em lista. O fix normaliza todas EXCETO as interativas não-Flow
(buttons/list), cujo content em lista É a estrutura voltada ao cidadão.
"""

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from engine.monitored_tool_node import MonitoredToolNode


@tool
def _noop_tool(x: str) -> str:
    """Tool trivial só pra instanciar o MonitoredToolNode."""
    return x


def _node() -> MonitoredToolNode:
    return MonitoredToolNode([_noop_tool])


def test_b1_non_interactive_tool_list_content_is_normalized():
    """B1: tool NÃO-interativa com content `["texto"]` (shape do adapter MCP) é
    normalizada pro 1º item. É o caminho live da luminária (multi_step_service);
    antes do fix só o Flow era normalizado e as demais iam ao LLM como lista."""
    node = _node()
    msg = ToolMessage(
        content=["resultado-real"],
        name="multi_step_service",
        tool_call_id="call_1",
    )
    node._postprocess_tool_messages({"messages": [msg]})
    assert msg.content == "resultado-real"


def test_flow_interactive_tool_content_is_normalized():
    """Regressão: a interativa Flow continua normalizada (content[0] = envelope)."""
    node = _node()
    msg = ToolMessage(
        content=[{"type": "interactive"}],
        name="build_whatsapp_flow_envelope",
        tool_call_id="call_2",
    )
    node._postprocess_tool_messages({"messages": [msg]})
    assert msg.content == {"type": "interactive"}


def test_non_flow_interactive_tools_keep_list_content():
    """Carve-out preservado: buttons/list mantêm o content em lista (é a estrutura
    interativa voltada ao cidadão) — NÃO devem ser normalizados."""
    node = _node()
    for name in ("send_whatsapp_list", "send_whatsapp_buttons"):
        msg = ToolMessage(
            content=[{"type": "text", "text": "Escolha uma opção"}],
            name=name,
            tool_call_id=f"call-{name}",
        )
        node._postprocess_tool_messages({"messages": [msg]})
        assert msg.content == [{"type": "text", "text": "Escolha uma opção"}], name


def test_postprocess_sets_timestamp_and_keeps_string_content():
    """content string (não-lista) fica intacto; timestamp é setado."""
    node = _node()
    msg = ToolMessage(content="ja-string", name="google_search", tool_call_id="call_3")
    node._postprocess_tool_messages({"messages": [msg]})
    assert msg.content == "ja-string"
    assert "timestamp" in msg.additional_kwargs


def test_postprocess_does_not_break_on_empty_list():
    """Lista vazia não deve quebrar (guard `and message.content`)."""
    node = _node()
    msg = ToolMessage(content=[], name="equipments", tool_call_id="call_4")
    node._postprocess_tool_messages({"messages": [msg]})
    assert msg.content == []
