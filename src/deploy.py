from datetime import datetime

import vertexai
from vertexai import agent_engines

from engine.agent import Agent
from src.config import env
from src.prompt import prompt_data

vertexai.init(
    project=env.PROJECT_ID,
    location=env.LOCATION,
    staging_bucket=env.GCS_BUCKET,
)


def deploy():
    system_prompt = prompt_data["prompt"]
    system_prompt_version = prompt_data["version"]
    model = "gemini-2.5-flash"
    now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    # Tools will be loaded at runtime from MCP server (not at deployment time)
    # This allows deployment from local machine where MCP private network is not accessible
    local_agent = Agent(
        model=model,
        system_prompt=system_prompt,
        include_thoughts=True,
        thinking_budget=-1,  # 0 to disable, -1 to unlimited and other token limit value
        temperature=0.7,
        tools=[],  # Empty - tools loaded lazily at runtime
        otpl_service=f"eai-langgraph-v{system_prompt_version}",
    )
    service_account = f"{env.PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

    # VPC network configuration for private MCP server access
    # IMPORTANT: psc_interface_config affects ALL network connections from the agent,
    # not just MCP calls. This includes:
    # - PostgreSQL/Cloud SQL connections
    # - External API calls
    # - DNS resolution
    # 
    # When enabled, the network_attachment determines ALL routing, and dns_peering_configs
    # affects ALL DNS lookups. This can cause issues if:
    # 1. Cloud SQL is not accessible from the PSC network
    # 2. DNS peering interferes with Cloud SQL DNS resolution
    # 3. Network routes don't include paths to Cloud SQL
    # 
    # Solution options:
    # A) Keep PSC disabled and use MCP_SERVER_PUBLIC_URL (current working solution)
    # B) Configure PSC network to allow Cloud SQL access
    # C) Use Cloud SQL Private IP and add appropriate routes to PSC network
    psc_config = None
    if hasattr(env, "NETWORK_ATTACHMENT") and env.NETWORK_ATTACHMENT:
        psc_config = {
            "network_attachment": env.NETWORK_ATTACHMENT,
            "dns_peering_configs": [
                {
                    "domain": "agent-engine.internal",
                    "target_project": env.PROJECT_ID,
                    "target_network": "application-network",
                },
            ],
        }

    return agent_engines.create(
        local_agent,
        requirements=[
            "cloudpickle==3.1.2",
            "google-cloud-aiplatform[agent-engines]==1.135.0",
            "httpx>=0.27.0",
            "langchain==1.2.7",
            "langchain-core==1.2.7",
            "langchain-google-genai==2.1.12",
            "langchain-google-vertexai==2.1.2",
            "langchain-mcp-adapters==0.2.0",
            "langgraph==1.0.8",
            "langgraph-checkpoint==4.0.0",
            "langgraph-checkpoint-postgres==3.0.4",
            "langgraph-prebuilt==1.0.7",
            "loguru==0.7.3",
            "mcp==1.26.0",
            "opentelemetry-exporter-otlp-proto-http==1.38.0",
            "opentelemetry-instrumentation-langchain==0.51.1",
            "opentelemetry-sdk==1.38.0",
            "psycopg[binary]==3.3.2",
            "psycopg-pool==3.3.0",
            "pydantic==2.12.5",
            "python-dotenv>=1.0.0",
            "typing-extensions>=4.14.0",
        ],
        extra_packages=["./engine"],
        gcs_dir_name=f"{model}/v{system_prompt_version}/{now}",
        display_name=f"EAI Agent | {model} | v{system_prompt_version}",
        env_vars={
            "PROJECT_ID": env.PROJECT_ID,
            "LOCATION": env.LOCATION,
            "INSTANCE": env.INSTANCE,
            "DATABASE_HOST": "10.0.0.54",  # Direct IP instead of postgres.agent-engine.internal
            "DATABASE_PORT": env.DATABASE_PORT,
            "DATABASE": env.DATABASE,
            "DATABASE_USER": env.DATABASE_USER,
            "DATABASE_PASSWORD": env.DATABASE_PASSWORD,
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": env.OTEL_EXPORTER_OTLP_TRACES_HEADERS,
            "MCP_SERVER_URL": env.MCP_SERVER_URL,
            "MCP_API_TOKEN": env.MCP_API_TOKEN,
            "EAI_AGENT_URL": env.EAI_AGENT_URL,
            "EAI_AGENT_TOKEN": env.EAI_AGENT_TOKEN,
            "SHORT_MEMORY_TOKEN_LIMIT": env.SHORT_MEMORY_TOKEN_LIMIT,
            "SHORT_MEMORY_TIME_LIMIT": env.SHORT_MEMORY_TIME_LIMIT,
            "MCP_EXCLUDED_TOOLS": ",".join(env.MCP_EXCLUDED_TOOLS)
            if env.MCP_EXCLUDED_TOOLS
            else "",
            "ERROR_INTERCEPTOR_URL": env.ERROR_INTERCEPTOR_URL,
            "ERROR_INTERCEPTOR_TOKEN": env.ERROR_INTERCEPTOR_TOKEN,
        },
        service_account=service_account,
        psc_interface_config=psc_config,
    )


if __name__ == "__main__":
    deploy()
