### Use private MCP URL not to go through Google Cloud Armor ###

from typing import List, Optional
from langchain_core.tools import BaseTool
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from engine.log import logger
import json


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
    logger.info("[MCP Tools] Starting MCP tools loading process")
    
    # Initialize default values
    if include_tools is None:
        include_tools = []
    if exclude_tools is None:
        exclude_tools = []

    # Log filtering parameters
    if include_tools:
        logger.info(f"[MCP Tools] Include filter: {include_tools}")
    if exclude_tools:
        logger.info(f"[MCP Tools] Exclude filter: {exclude_tools}")

    # Read from environment variables (works in both local and deployed environments)
    mcp_url = os.getenv("MCP_SERVER_URL")
    mcp_token = os.getenv("MCP_API_TOKEN")
    
    logger.info(f"[MCP Tools] MCP_SERVER_URL: {mcp_url}")
    logger.info(f"[MCP Tools] MCP_API_TOKEN: {'SET' if mcp_token else 'NOT SET'}")
    
    if not mcp_url:
        error_msg = "[MCP Tools] ERROR: MCP_SERVER_URL environment variable is not set"
        logger.error(error_msg)
        raise ValueError("MCP_SERVER_URL environment variable must be set")
    
    if not mcp_token:
        error_msg = "[MCP Tools] ERROR: MCP_API_TOKEN environment variable is not set"
        logger.error(error_msg)
        raise ValueError("MCP_API_TOKEN environment variable must be set")

    try:
        logger.info(f"[MCP Tools] Creating MultiServerMCPClient for URL: {mcp_url}")
        
        # Log the full client configuration (except sensitive token)
        client_config = {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": mcp_url,
                "headers": {
                    "Authorization": f"Bearer {mcp_token[:10]}..." if mcp_token else "NOT SET",
                },
            }
        }
        logger.info(f"[MCP Tools] Client configuration: {client_config}")
        
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
        logger.info("[MCP Tools] MultiServerMCPClient created successfully")
    except Exception as e:
        logger.error(f"[MCP Tools] ERROR: Failed to create MCP client: {type(e).__name__}: {str(e)}", exc_info=True)
        raise

    try:
        logger.info(f"[MCP Tools] Fetching tools from MCP server at {mcp_url}")
        logger.info("[MCP Tools] Calling client.get_tools() - this will send a tools/list request to the MCP server")
        logger.info("[MCP Tools] MCP Protocol: The request will be a JSON-RPC 2.0 message with method 'tools/list'")
        
        # Log what we're about to request
        logger.info("[MCP Tools] Expected JSON-RPC request structure:")
        logger.info("[MCP Tools]   - jsonrpc: '2.0'")
        logger.info("[MCP Tools]   - method: 'tools/list'")
        logger.info("[MCP Tools]   - params: {} (empty params for tools/list)")
        logger.info(f"[MCP Tools]   - Authorization header: Bearer {mcp_token[:10]}...")
        
        try:
            tools = await client.get_tools()
            logger.info(f"[MCP Tools] Successfully fetched {len(tools)} tools from server")
        except Exception as get_tools_error:
            logger.error(f"[MCP Tools] ERROR during get_tools() call:")
            logger.error(f"[MCP Tools]   Error Type: {type(get_tools_error).__name__}")
            logger.error(f"[MCP Tools]   Error Message: {str(get_tools_error)}")
            logger.error(f"[MCP Tools]   Error Details: {repr(get_tools_error)}")
            
            # Try to extract more information from the error
            if hasattr(get_tools_error, 'args'):
                logger.error(f"[MCP Tools]   Error Args: {get_tools_error.args}")
            if hasattr(get_tools_error, '__dict__'):
                logger.error(f"[MCP Tools]   Error Attributes: {get_tools_error.__dict__}")
            
            logger.error("[MCP Tools] This error suggests the MCP server rejected the request.")
            logger.error("[MCP Tools] Common causes:")
            logger.error("[MCP Tools]   1. Invalid Authorization token")
            logger.error("[MCP Tools]   2. MCP server expects different request format")
            logger.error("[MCP Tools]   3. Server-side validation failed")
            logger.error("[MCP Tools]   4. Network/connectivity issues")
            
            raise
        
        # Log all tool names received
        tool_names = [tool.name for tool in tools]
        logger.info(f"[MCP Tools] All available tools: {tool_names}")
        
    except Exception as e:
        logger.error(
            f"[MCP Tools] ERROR: Failed to fetch tools from {mcp_url}. "
            f"Error type: {type(e).__name__}, Message: {str(e)}",
            exc_info=True
        )
        logger.error(f"[MCP Tools] Full exception details:", exc_info=True)
        raise

    # Apply filtering logic
    try:
        if include_tools:
            # If include list is not empty, return only tools in the include list
            filtered_tools = [tool for tool in tools if tool.name in include_tools]
            logger.info(f"[MCP Tools] Applied include filter. Included {len(filtered_tools)} tools")
        elif exclude_tools:
            # If exclude list is not empty, return all tools except the ones in exclude list
            filtered_tools = [tool for tool in tools if tool.name not in exclude_tools]
            excluded_count = len(tools) - len(filtered_tools)
            logger.info(f"[MCP Tools] Applied exclude filter. Excluded {excluded_count} tools, kept {len(filtered_tools)} tools")
        else:
            # If both lists are empty, return all tools
            filtered_tools = tools
            logger.info(f"[MCP Tools] No filtering applied. Returning all {len(filtered_tools)} tools")
        
        # Log final tool names that will be returned
        final_tool_names = [tool.name for tool in filtered_tools]
        logger.info(f"[MCP Tools] Final tools to be loaded: {final_tool_names}")
        logger.info(f"[MCP Tools] Successfully completed MCP tools loading. Total tools: {len(filtered_tools)}")
        
        return filtered_tools
        
    except Exception as e:
        logger.error(
            f"[MCP Tools] ERROR: Failed to filter tools. "
            f"Error type: {type(e).__name__}, Message: {str(e)}",
            exc_info=True
        )
        raise
