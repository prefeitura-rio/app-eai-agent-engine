from typing import List
from langchain_core.tools import BaseTool
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import env


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


mcp_tools = asyncio.run(get_mcp_tools())
