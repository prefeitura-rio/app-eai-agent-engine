import asyncio
from os import getenv
from typing import Any, Callable, Iterator, List, Sequence

import vertexai
from langchain.load.dump import dumpd
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool
from langchain_google_vertexai import ChatVertexAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from vertexai import agent_engines

def getenv_or_action(
    env_name: str, *, action: str = "raise", default: str = None
) -> str:
    """Get an environment variable or raise an exception.

    Args:
        env_name (str): The name of the environment variable.
        action (str, optional): The action to take if the environment variable is not set.
            Defaults to "raise".
        default (str, optional): The default value to return if the environment variable is not set.
            Defaults to None.

    Raises:
        ValueError: If the action is not one of "raise", "warn", or "ignore".

    Returns:
        str: The value of the environment variable, or the default value if the environment variable
            is not set.
    """
    if action not in ["raise", "warn", "ignore"]:
        raise ValueError("action must be one of 'raise', 'warn', or 'ignore'")

    # Tenta obter a variável do ambiente
    value = getenv(env_name, None)

    # Se ainda não encontrou, aplica a ação especificada
    if value is None:
        if action == "raise":
            raise EnvironmentError(f"Environment variable {env_name} is not set.")
        elif action == "warn":
            print.warning(f"Warning: Environment variable {env_name} is not set.")
    return value

MPC_SERVER_URL = getenv_or_action("MPC_SERVER_URL")
MPC_API_TOKEN = getenv_or_action("MPC_API_TOKEN")

GEMINI_API_KEY = getenv_or_action("GEMINI_API_KEY")
PROJECT_ID = getenv_or_action("PROJECT_ID")
PROJECT_NUMBER = getenv_or_action("PROJECT_NUMBER")
LOCATION = getenv_or_action("LOCATION")
INSTANCE = getenv_or_action("INSTANCE")
DATABASE = getenv_or_action("DATABASE")
DATABASE_USER = getenv_or_action("DATABASE_USER")
DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD")
GCS_BUCKET = getenv_or_action("GCS_BUCKET")
GCS_BUCKET_STAGING = getenv_or_action("GCS_BUCKET_STAGING")

DATABASE_PASSWORD = getenv_or_action("DATABASE_PASSWORD")

PG_URI = getenv_or_action("PG_URI", action="ignore")

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
                "url": MPC_SERVER_URL,
                "headers": {
                    "Authorization": f"Bearer {MPC_API_TOKEN}",
                },
            },
        }
    )
    tools = await client.get_tools()
    return tools


mcp_tools = asyncio.run(get_mcp_tools())

vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=GCS_BUCKET_STAGING,
)

class Agent:
    def __init__(
        self,
        *,
        model: str,
    ):
        self._model: str = model
        self._tools: Sequence[Callable] = mcp_tools
        self._graph: CompiledGraph = None

    def set_up(self):
        llm = ChatVertexAI(model_name=self._model)
        llm_with_tools = llm.bind_tools(tools=self._tools)
        self._graph = create_react_agent(llm_with_tools, self._tools)

    def query(self, **kwargs) -> dict[str, Any] | Any:
        return self._graph.invoke(**kwargs)

    def stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        for chunk in self._graph.stream(**kwargs):
            yield dumpd(chunk)

    async def async_query(self, **kwargs) -> dict[str, Any] | Any:
        return await self._graph.ainvoke(**kwargs)

    async def async_stream_query(self, **kwargs) -> Iterator[dict[str, Any] | Any]:
        async for chunk in self._graph.astream(**kwargs):
            yield dumpd(chunk)

def deploy(model: str = "gemini-2.5-flash"):
    local_agent = Agent(model=model)
    return agent_engines.create(
        local_agent,
        requirements=[
            "langchain-mcp-adapters>=0.1.9",
            "cloudpickle>=3.1.1",
            "google-cloud-aiplatform[agent-engines,langchain]>=1.106.0",
            "langchain>=0.3.27",
            "langchain-core>=0.3.72",
            "langchain-google-cloud-sql-pg>=0.14.1",
            "langchain-google-genai>=2.1.9",
            "langchain-google-vertexai>=2.0.28",
            "langchain-mcp-adapters>=0.1.9",
        ],
        gcs_dir_name=GCS_BUCKET,
        display_name="EAI Agent",
        env_vars={
            "MCP_SERVER_URL": MPC_SERVER_URL,
            "MCP_SERVER_TOKEN": MPC_API_TOKEN,
        },
        service_account="989726518247-compute@developer.gserviceaccount.com",
    )


if __name__ == "__main__":
    deploy()