"""Testes do hook de injeção de identificador (``engine.agent.Agent``).

``_inject_thread_id_in_user_id_params`` reescreve ``user_id`` E ``user_number``
nas tool calls com o ``thread_id`` (telefone do cidadão, vindo do
``config.configurable``), pra que as tools de auth gov.br
(``govbr_auth_init/status/logout`` — que usam ``user_number``) recebam o número
correto sem o LLM precisar adivinhá-lo em fluxos de texto.

O método não usa ``self``, então é chamável unbound com ``self=None`` — evita
instanciar o Agent (que exige env/GCP).
"""

from engine.agent import Agent

_THREAD = "5521999999999"


class _AIMsg:
    """Stub mínimo de AIMessage que carrega ``tool_calls``."""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def _inject(tool_calls, thread_id=_THREAD, configurable=None):
    state = {"messages": [_AIMsg(tool_calls)]}
    config = {"configurable": configurable if configurable is not None else {"thread_id": thread_id}}
    Agent._inject_thread_id_in_user_id_params(None, state, config)
    return tool_calls


def test_injects_user_number_for_govbr_tools():
    # o caso que estava quebrado: gov.br tools usam user_number.
    tc = [{"name": "govbr_auth_status", "args": {"user_number": "PLACEHOLDER"}}]
    _inject(tc)
    assert tc[0]["args"]["user_number"] == _THREAD


def test_still_injects_user_id():
    tc = [{"name": "multi_step_service", "args": {"user_id": "X", "service_name": "reparo"}}]
    _inject(tc)
    assert tc[0]["args"]["user_id"] == _THREAD
    assert tc[0]["args"]["service_name"] == "reparo"  # demais args intactos


def test_injects_both_params_in_same_call():
    tc = [{"name": "weird_tool", "args": {"user_id": "A", "user_number": "B"}}]
    _inject(tc)
    assert tc[0]["args"]["user_id"] == _THREAD
    assert tc[0]["args"]["user_number"] == _THREAD


def test_no_thread_id_leaves_args_untouched():
    tc = [{"name": "govbr_auth_status", "args": {"user_number": "PLACEHOLDER"}}]
    _inject(tc, configurable={})  # sem thread_id
    assert tc[0]["args"]["user_number"] == "PLACEHOLDER"


def test_tool_without_id_param_untouched():
    tc = [{"name": "get_info", "args": {"query": "horario"}}]
    _inject(tc)
    assert tc[0]["args"] == {"query": "horario"}
