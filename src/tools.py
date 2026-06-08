### Use public MCP URL for local testing ###

from typing import List, Optional
from langchain_core.tools import BaseTool
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import env
from engine.interactive_tools import mark_interactive_tools_return_direct


from src.utils.log import logger

# Use public URL for local testing (private URL not accessible from local machine)
logger.debug(f"Local testing MCP URL: {env.MCP_SERVER_PUBLIC_URL}")


async def get_mcp_tools(
    include_tools: Optional[List[str]] = None, exclude_tools: Optional[List[str]] = None
) -> List[BaseTool]:
    """
    Inicializa o cliente MCP e busca as ferramentas disponíveis de forma assíncrona.

    Args:
        include_tools (List[str], optional): Lista de nomes de ferramentas para incluir.
                                           Se fornecida, apenas essas ferramentas serão retornadas.
        exclude_tools (List[str], optional): Lista de nomes de ferramentas para excluir.
                                           Se fornecida, todas as ferramentas exceto essas serão retornadas.

    Returns:
        List[BaseTool]: Lista de ferramentas disponíveis do servidor MCP, filtrada conforme os parâmetros
    """
    # Initialize default values
    if include_tools is None:
        include_tools = []
    if exclude_tools is None:
        exclude_tools = []

    # Use public URL for local testing (MCP_SERVER_URL is private and not accessible locally)
    client = MultiServerMCPClient(
        {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": env.MCP_SERVER_PUBLIC_URL,
                "headers": {
                    "Authorization": f"Bearer {env.MCP_API_TOKEN}",
                },
            },
        }
    )
    tools = await client.get_tools()

    # Apply filtering logic
    if include_tools:
        # If include list is not empty, return only tools in the include list
        filtered_tools = [tool for tool in tools if tool.name in include_tools]
    elif exclude_tools:
        # If exclude list is not empty, return all tools except the ones in exclude list
        filtered_tools = [tool for tool in tools if tool.name not in exclude_tools]
    else:
        # If both lists are empty, return all tools
        filtered_tools = tools

    return mark_interactive_tools_return_direct(filtered_tools)

# Safety exclusions aplicadas no loader compartilhado — afeta todos os
# caminhos (deploy, interactive_test, pre_deploy tests). Mantém estes
# nomes fora do tool binding mesmo se o operator não os listou em
# MCP_EXCLUDED_TOOLS.
#
# `send_whatsapp_flow` (high-level pós-rename MCP 2026-05-18): requer
# `user_number` E.164 que o Engine framework não injeta deterministicamente
# (langgraph-prebuilt 1.0.7 não tem inject_tool_args). LLM pode hallucinar
# número e mandar Flow pra cidadão errado. Bloqueado até injeção segura
# estar wired (ex: HTTP header X-User-Number derivado de thread_id).
#
# Migration alias: deployments preexistentes que tinham `send_whatsapp_flow`
# (nome antigo do low-level) em MCP_EXCLUDED_TOOLS devem manter a low-level
# bloqueada pós-rename — automaticamente também excluímos
# `build_whatsapp_flow_envelope`.
_SAFETY_EXCLUDED = ["send_whatsapp_flow"]
_legacy_excluded = list(env.MCP_EXCLUDED_TOOLS or [])
if (
    "send_whatsapp_flow" in _legacy_excluded
    and "build_whatsapp_flow_envelope" not in _legacy_excluded
):
    _SAFETY_EXCLUDED.append("build_whatsapp_flow_envelope")

_effective_excluded = sorted(set(_legacy_excluded) | set(_SAFETY_EXCLUDED))

mcp_tools = asyncio.run(get_mcp_tools(exclude_tools=_effective_excluded))
