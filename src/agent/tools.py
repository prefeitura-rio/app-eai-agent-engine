from src.config import env
from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio
from typing import List
from langchain_core.tools import BaseTool


async def get_mcp_tools() -> List[BaseTool]:
    """
    Inicializa o cliente MCP e busca as ferramentas disponíveis de forma assíncrona.

    Returns:
        List[BaseTool]: Lista de ferramentas disponíveis do servidor MCP
    """
    client = MultiServerMCPClient(
        {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": env.MPC_SERVER_URL,
                "headers": {
                    "Authorization": f"Bearer {env.MPC_API_TOKEN}",
                },
            },
        }
    )
    tools = await client.get_tools()
    return tools


def get_mcp_tools_sync() -> List[BaseTool]:
    """
    Versão síncrona para obter as ferramentas MCP.
    Útil para contextos onde async/await não é suportado.

    Returns:
        List[BaseTool]: Lista de ferramentas disponíveis do servidor MCP
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    tools = loop.run_until_complete(get_mcp_tools())
    return tools
