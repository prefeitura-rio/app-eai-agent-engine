"""Testes da resiliência do engine a erro de tool (fix do bug do pin de
localização / luminária):

- A: query()/async_query() devolvem fallback amigável em vez de propagar a
  exceção (que viraria o erro genérico do Gateway) E ainda reportam ao
  interceptor (monitoramento não some por causa do catch).
- B: MonitoredToolNode reporta erros de tool sobrescrevendo _func/_afunc (os
  métodos reais do langgraph 1.x; a versão antiga sobrescrevia _run/_arun, que
  o base nunca chama — monitoramento morto). Nesta versão do langgraph o
  handle_tool_errors default RE-LEVANTA exceções do corpo da tool (só converte
  ToolInvocationError), então o override reporta no caminho de propagação e
  re-levanta — deixando a UX pra rede de segurança do Agent.query.
"""

import asyncio

import pytest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import Send

import engine.monitored_tool_node as mtn
from engine.monitored_tool_node import MonitoredToolNode


@tool
def failing_tool(x: str) -> str:
    """Tool que sempre falha (para testar resiliência)."""
    raise RuntimeError("simulated tool failure")


def _build_graph_with_node(node):
    """Mini-grafo: nó semente injeta um tool_call, depois roda o ToolNode.

    Roda dentro de um StateGraph compilado (não standalone) porque é só aí que o
    langgraph popula o Runtime que `_afunc`/`_func` exigem — fiel à produção.
    """

    def seed(state):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "failing_tool", "args": {"x": "y"}, "id": "call_1"}
                    ],
                )
            ]
        }

    g = StateGraph(MessagesState)
    g.add_node("seed", seed)
    g.add_node("tools", node)
    g.add_edge(START, "seed")
    g.add_edge("seed", "tools")
    g.add_edge("tools", END)
    return g.compile()


def _build_graph_with_send_dispatch(node):
    """Mini-grafo que despacha pro ToolNode via `Send("tools", [tool_call])`.

    Replica EXATAMENTE o routing v2 do engine (custom_react_agent.py:906/988):
    o nó "tools" recebe `[tool_call_dict]` (lista), não o state — o path real de
    produção. Garante que `_pending_tool_names` extraia o nome por dentro do
    `_afunc`/grafo, não só no helper isolado.
    """

    def seed(state):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "failing_tool", "args": {"x": "y"}, "id": "call_1"}
                    ],
                )
            ]
        }

    def route(state):
        last = state["messages"][-1]
        return [Send("tools", [tc]) for tc in last.tool_calls]

    g = StateGraph(MessagesState)
    g.add_node("seed", seed)
    g.add_node("tools", node)
    g.add_edge(START, "seed")
    g.add_conditional_edges("seed", route, ["tools"])
    g.add_edge("tools", END)
    return g.compile()


def test_monitored_tool_node_reports_propagating_tool_error():
    """B: exceção no corpo da tool propaga (default handle_tool_errors) E é reportada.

    Esse é o caso comum em produção: nesta versão do langgraph a exceção é
    re-levantada pelo base. O override precisa reportá-la (monitoramento) e
    re-levantar (a rede de segurança do Agent.query trata a UX).
    """
    app = _build_graph_with_node(MonitoredToolNode([failing_tool]))

    async def run():
        # patch() auto-usa AsyncMock porque send_general_error é coroutine.
        with patch.object(mtn, "send_general_error") as mock_report:
            with pytest.raises(Exception):  # a exceção da tool propaga
                await app.ainvoke(
                    {"messages": []},
                    config={"configurable": {"thread_id": "5521999999999"}},
                )
            return mock_report

    mock_report = asyncio.run(run())

    # monitoramento disparou (override _afunc é o método real, não código morto)
    assert mock_report.await_count >= 1 or mock_report.call_count >= 1
    # e o report identifica a tool que falhou + carrega a mensagem do erro
    reported = str(mock_report.call_args)
    assert "simulated tool failure" in reported
    assert "failing_tool" in reported  # nome extraído do input, não "unknown"


def test_monitored_tool_node_reports_via_send_dispatch_v2():
    """B (path de produção): com Send("tools", [tool_call]) o nó recebe a LISTA
    de tool_call dicts — o input v2 real. O erro deve propagar E ser reportado
    com o nome da tool extraído por dentro do _afunc (não "unknown")."""
    app = _build_graph_with_send_dispatch(MonitoredToolNode([failing_tool]))

    async def run():
        with patch.object(mtn, "send_general_error") as mock_report:
            with pytest.raises(Exception):
                await app.ainvoke(
                    {"messages": []},
                    config={"configurable": {"thread_id": "5521999999999"}},
                )
            return mock_report

    mock_report = asyncio.run(run())

    assert mock_report.await_count >= 1 or mock_report.call_count >= 1
    reported = str(mock_report.call_args)
    assert "failing_tool" in reported  # nome extraído do [tool_call] via _afunc
    assert "simulated tool failure" in reported


def test_pending_tool_names_handles_v2_and_state_inputs():
    """B': nome da tool é extraído nos dois formatos de input do ToolNode.

    v2 (produção) entrega `[tool_call_dict]` via Send; v1/state entrega
    `{"messages": [...]}`. Ambos devem render o nome real, nunca "unknown".
    """
    node = MonitoredToolNode([failing_tool])

    # v2: lista de tool-call dicts diretos (path de produção via Send)
    v2_input = [{"name": "reverse_geocode_address", "args": {}, "id": "c1"}]
    assert node._pending_tool_names(v2_input) == "reverse_geocode_address"

    # state dict com AIMessage
    state_input = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "create_ticket", "args": {}, "id": "c2"}],
            )
        ]
    }
    assert node._pending_tool_names(state_input) == "create_ticket"

    # input opaco → degrada para "unknown" sem levantar
    assert node._pending_tool_names(object()) == "unknown"


def test_query_returns_fallback_on_graph_error():
    """A: query() devolve a mensagem de fallback quando o grafo levanta.

    query() está em Agent (decorada com @interceptor, que repassa em caso de
    sucesso). Em vez de construir o Agent inteiro (pesado: Vertex/checkpointer),
    invocamos Agent.query bound a um fake self com só os atributos que o caminho
    de erro toca.
    """
    from types import SimpleNamespace

    from engine.agent import Agent, ENGINE_FALLBACK_MESSAGE

    class _BoomGraph:
        def invoke(self, **kwargs):
            raise RuntimeError("graph boom")

    fake_self = SimpleNamespace(
        _graph=_BoomGraph(),
        _combined_pre_invoke_hook=lambda **kw: kw,
        _ensure_sync_setup=lambda: None,
        _filter_current_interaction=lambda r: r,
        _trace_conversation=lambda r, **kw: None,
    )

    import engine.agent as agent_mod

    with patch.object(agent_mod, "send_general_error") as mock_report:
        result = Agent.query(
            fake_self,
            input={"messages": []},
            config={"configurable": {"thread_id": "test"}},
        )

    messages = result["messages"]
    assert isinstance(messages[0], AIMessage)
    assert messages[0].content == ENGINE_FALLBACK_MESSAGE
    # a rede de segurança devolve fallback MAS preserva o monitoramento:
    # o erro de grafo é reportado ao interceptor (não some).
    assert mock_report.await_count >= 1 or mock_report.call_count >= 1
