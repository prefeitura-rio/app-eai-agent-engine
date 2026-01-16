### Use private MCP URL not to go through Google Cloud Armor ###

from typing import List, Optional
from langchain_core.tools import BaseTool
import os
from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_mcp_tools(
    include_tools: Optional[List[str]] = None,
    exclude_tools: Optional[List[str]] = None,
) -> List[BaseTool]:
    """
    Load MCP tools from server URL specified in environment variables.
    
    This function reads MCP_SERVER_URL and MCP_API_TOKEN from environment variables,
    allowing different URLs in local development vs deployed environments.

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

    # Read from environment variables (works in both local and deployed environments)
    mcp_url = os.getenv("MCP_SERVER_URL")
    mcp_token = os.getenv("MCP_API_TOKEN")
    
    if not mcp_url or not mcp_token:
        raise ValueError("MCP_SERVER_URL and MCP_API_TOKEN environment variables must be set")

    client = MultiServerMCPClient(
        {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": mcp_url,
                "headers": {
                    "Authorization": f"Bearer {mcp_token}",
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

    return filtered_tools
