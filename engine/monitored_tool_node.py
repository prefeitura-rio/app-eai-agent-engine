"""
Monitored Tool Node

Wrapper do ToolNode do LangGraph que reporta erros de execução de tool ao
interceptor de erros, dando visibilidade de quais tools falham e por quê.

IMPORTANTE (langgraph 1.x): os entry-points do ToolNode são `_func`/`_afunc`
(NÃO `_run`/`_arun`). A versão anterior sobrescrevia `_run`/`_arun`, que o base
nunca chama — ou seja, o monitoramento estava silenciosamente morto.

Esta versão sobrescreve os métodos corretos cobrindo os DOIS caminhos pelos
quais um erro de tool aparece nesta versão do langgraph:

1. **Exceção propagada** — com o `handle_tool_errors` default, uma exceção
   levantada no corpo da tool (ex.: Google Maps fora do ar em
   `reverse_geocode_address`) é RE-LEVANTADA pelo base, não convertida. O
   override captura, reporta e re-levanta (a rede de segurança do Agent.query
   converte em fallback amigável pro cidadão). Esse é o caso comum.
2. **ToolMessage(status="error")** — quando o erro É convertido (ex.:
   ToolInvocationError, ou handle_tool_errors configurado como bool/str), ele
   chega como ToolMessage no resultado. O override inspeciona e reporta.

O override é PASSTHROUGH: não altera o error handling do base — só dá
observabilidade. A recuperação de UX fica com `Agent.query` (rede de segurança).
"""

import asyncio
from typing import Any, List, Tuple

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.runtime import Runtime

from engine.utils import send_general_error, make_tool_source
from engine.log import logger

# Retém referência forte dos reports fire-and-forget. asyncio só mantém weakref
# do task de create_task — sem isso, se o caller retorna antes do report
# completar, o task pode ser coletado e o erro de tool nunca chega ao monitor.
_PENDING_REPORT_TASKS: set = set()


class MonitoredToolNode(ToolNode):
    """ToolNode que reporta erros de execução de tool sem alterar o comportamento.

    As assinaturas de `_func`/`_afunc` espelham EXATAMENTE as do base, incluindo
    anotações (`config: RunnableConfig`, `runtime: Runtime`). O langgraph inspeciona
    essas anotações para injetar config/runtime; com `Any`, ele trata `runtime`
    como config key e levanta "Missing required config key" — quebraria em produção.
    """

    async def _afunc(
        self, input: Any, config: RunnableConfig, runtime: Runtime
    ) -> Any:
        try:
            result = await super()._afunc(input, config, runtime)
        except Exception as exc:
            await self._report(self._pending_tool_names(input), repr(exc), config)
            raise
        for tool_name, content in self._extract_tool_errors(result):
            await self._report(tool_name, content, config)
        return result

    def _func(self, input: Any, config: RunnableConfig, runtime: Runtime) -> Any:
        try:
            result = super()._func(input, config, runtime)
        except Exception as exc:
            self._report_sync(
                [(self._pending_tool_names(input), repr(exc))], config
            )
            raise
        errors = self._extract_tool_errors(result)
        if errors:
            self._report_sync(errors, config)
        return result

    # ------------------------------------------------------------------ helpers

    def _pending_tool_names(self, input: Any) -> str:
        """Nomes dos tool_calls que o ToolNode ia executar, extraídos do input.

        Quando a tool levanta no corpo, o base re-levanta antes de qualquer
        ToolMessage existir — então o nome da tool tem que vir do input. O ToolNode
        recebe o input em dois formatos:

        - **v2 (default do react agent)**: o routing faz `Send("tools", [tool_call])`,
          então `input` é uma LISTA de dicts de tool_call diretos (`{"name", "args",
          "id"}`). Esse é o path de produção.
        - **v1 / state**: `input` é o state (`{"messages": [...]}`) ou uma lista de
          mensagens; o nome vem dos `tool_calls` da última AIMessage.

        Com 1 call é exato; com vários, junta os nomes para o alerta apontar o
        conjunto que falhou.
        """
        try:
            if isinstance(input, dict):
                messages = input.get(self._messages_key, []) or []
            elif isinstance(input, list):
                # v2: itens são dicts de tool_call diretos (têm "name", não .tool_calls)
                direct = [
                    str(item["name"])
                    for item in input
                    if isinstance(item, dict) and item.get("name")
                ]
                if direct:
                    return ",".join(direct)
                messages = input
            else:
                return "unknown"
            for msg in reversed(messages):
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    names = [str(tc["name"]) for tc in tool_calls if tc.get("name")]
                    if names:
                        return ",".join(names)
            return "unknown"
        except Exception:
            return "unknown"

    def _extract_tool_errors(self, result: Any) -> List[Tuple[str, str]]:
        """Extrai (tool_name, content) das ToolMessages com status='error'."""
        try:
            if isinstance(result, dict):
                messages = result.get(self._messages_key, []) or []
            elif isinstance(result, list):
                messages = result
            else:
                return []
            errors: List[Tuple[str, str]] = []
            for msg in messages:
                if (
                    isinstance(msg, ToolMessage)
                    and getattr(msg, "status", None) == "error"
                ):
                    errors.append(
                        (
                            getattr(msg, "name", None) or "unknown",
                            str(getattr(msg, "content", "")),
                        )
                    )
            return errors
        except Exception:
            return []

    async def _report(self, tool_name: str, content: str, config: Any) -> None:
        try:
            thread_id = "unknown"
            if isinstance(config, dict):
                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            await send_general_error(
                user_id=thread_id,
                source=make_tool_source(tool_name=tool_name),
                error_type="ToolExecutionError",
                error_message=content[:500],
                traceback=None,
            )
            logger.info(
                f"[Error Monitor] Tool error reportado: {tool_name} | {content[:100]}"
            )
        except Exception as report_error:
            logger.warning(
                f"[Error Monitor] Falha ao reportar erro de tool: {report_error}"
            )

    def _report_sync(self, errors: List[Tuple[str, str]], config: Any) -> None:
        """Reporta erros de tool a partir do caminho síncrono.

        Se há loop corrente, agenda (fire-and-forget). Senão (caso comum no path
        sync `graph.invoke`/`Agent.query`, ou em thread de executor), roda um loop
        efêmero via `asyncio.run` — sem isso o erro sync nunca chegaria ao monitor.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for tool_name, content in errors:
            if loop is not None:
                task = loop.create_task(self._report(tool_name, content, config))
                _PENDING_REPORT_TASKS.add(task)
                task.add_done_callback(_PENDING_REPORT_TASKS.discard)
            else:
                try:
                    asyncio.run(self._report(tool_name, content, config))
                except Exception as report_error:
                    logger.warning(
                        f"[Error Monitor] Falha ao reportar erro de tool (sync): "
                        f"{report_error}"
                    )
