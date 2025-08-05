read this to pages https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/develop/langgraph
https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/deploy 


now implement a langgraph react agent (from langgraph.prebuilt import create_react_agent) to be deployed in vertex agent engine, 
shoul have acess to tool from a tools.py with this tool:

from src.config import env
from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_mcp_tools():
    """
    Inicializa o cliente MCP e busca as ferramentas disponíveis de forma assíncrona.
    """
    client = MultiServerMCPClient(
        {
            "rio_mcp": {
                "transport": "streamable_http",
                "url": env.MCP_SERVER_URL,
                "headers": {
                    "Authorization": f"Bearer {env.MCP_API_TOKEN}",
                },
            },
        }
    )
    tools = await client.get_tools()
    return tools


agent.py with agent to be deployed ChatGoogleGenerativeAI with control over system prompt(file prompts.py), temperature, max_output_tokens, safety_settings

and deploy.py with the deploy code
