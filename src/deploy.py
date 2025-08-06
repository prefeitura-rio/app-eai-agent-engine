from src.tools import mcp_tools
from src.prompt import SYSTEM_PROMPT
from src.config import env
import vertexai
from vertexai import agent_engines
from engine.agent import Agent

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
    )
    return agent_engines.create(
        local_agent,
        requirements=[
            "cloudpickle>=3.1.1",
            "google-cloud-aiplatform[agent-engines]>=1.106.0",
            "langchain>=0.3.27",
            "langchain-core>=0.3.72",
            "langchain-google-cloud-sql-pg>=0.14.1",
            "langchain-google-genai>=2.1.9",
            "langchain-google-vertexai>=2.0.28",
            "langchain-mcp-adapters>=0.1.9",
            "langgraph>=0.6.3",
            "pydantic>=2.11.7",
        ],
        extra_packages=["./engine"],
        gcs_dir_name=env.GCS_BUCKET,
        display_name="EAI Agent",
        env_vars={
            # "MCP_SERVER_URL": env.MPC_SERVER_URL,
            # "MCP_SERVER_TOKEN": env.MPC_API_TOKEN,
            "PROJECT_ID": env.PROJECT_ID,
            "LOCATION": env.LOCATION,
            "INSTANCE": env.INSTANCE,
            "DATABASE": env.DATABASE,
            "DATABASE_USER": env.DATABASE_USER,
            "DATABASE_PASSWORD": env.DATABASE_PASSWORD,
        },
        service_account="989726518247-compute@developer.gserviceaccount.com",
    )


if __name__ == "__main__":
    deploy()
