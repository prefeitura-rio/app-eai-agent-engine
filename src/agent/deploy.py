import asyncio
from src.agent.prompt import SYSTEM_PROMPT
from src.agent.agent import Agent
from src.config import env
import vertexai
from vertexai import agent_engines
from src.agent.tools import mcp_tools

vertexai.init(
    project=env.PROJECT_ID,
    location=env.LOCATION,
    staging_bucket=env.GCS_BUCKET_STAGING,
)


def deploy():
    local_agent = Agent(
        model="gemini-2.5-flash",
        system_prompt=SYSTEM_PROMPT,
        tools=mcp_tools,
        temperature=0.7,
    )
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
        ],
        extra_packages=["./src"],
        gcs_dir_name=env.GCS_BUCKET,
        display_name="EAI Agent",
        env_vars={
            "MCP_SERVER_URL": env.MPC_SERVER_URL,
            "MCP_SERVER_TOKEN": env.MPC_API_TOKEN,
        },
        service_account="989726518247-compute@developer.gserviceaccount.com",
    )


if __name__ == "__main__":
    deploy()
