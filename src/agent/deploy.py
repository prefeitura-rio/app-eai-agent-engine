from typing import Sequence
from langchain import hub
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import BasePromptTemplate
from langchain_core.tools import BaseTool

from vertexai import agent_engines
from src.agent.tools import get_mcp_tools_sync
from src.config import env
import vertexai

vertexai.init(
    project=env.PROJECT_ID,
    location=env.LOCATION,
    staging_bucket=env.GCS_BUCKET_STAGING,
)

tools = get_mcp_tools_sync()


def react_builder(
    model: BaseLanguageModel,
    *,
    tools: Sequence[BaseTool],
    **kwargs,
):
    from langchain.agents.react.agent import create_react_agent
    from langchain.agents import AgentExecutor

    prompt = hub.pull("hwchase17/react")
    agent = create_react_agent(model, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, **kwargs)


local_agent = agent_engines.LanggraphAgent(
    model="gemini-2.5-flash",
    tools=tools,
    runnable_builder=react_builder,
)

remote_agent = agent_engines.create(
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
    # extra_packages=["langchain-mcp-adapters>=0.1.9"],
    gcs_dir_name=env.GCS_BUCKET,
    display_name="EAI Agent",
    env_vars={
        "MCP_SERVER_URL": env.MPC_SERVER_URL,
        "MCP_SERVER_TOKEN": env.MPC_API_TOKEN,
    },  # Optional.
    # build_options=build_options,  # Optional.
    service_account="989726518247-compute@developer.gserviceaccount.com",  # Optional.
)
