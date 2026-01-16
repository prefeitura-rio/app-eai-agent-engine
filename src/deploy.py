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
    psc_config = None
    if hasattr(env, "NETWORK_ATTACHMENT") and env.NETWORK_ATTACHMENT:
        from google.cloud.aiplatform_v1.types import PscInterfaceConfig
        
        psc_config = PscInterfaceConfig(
            network_attachment=env.NETWORK_ATTACHMENT,
            dns_peering_configs=[
                {
                    "domain": "mcp.internal.",
                    "target_project": env.PROJECT_ID,
                    "target_network": "application-network",
                },
            ],
        )

    return agent_engines.create(
        local_agent,
        requirements=[
            "cloudpickle>=3.1.1",
            "google-cloud-aiplatform[agent-engines]>=1.106.0",
            "httpx>=0.27.0",
            "langchain==0.3.27",
            "langchain-core==0.3.76",
            "langchain-google-cloud-sql-pg==0.14.1",
            "langchain-google-genai>=2.1.9",
            "langchain-google-vertexai==2.1.2",
            "langchain-mcp-adapters>=0.1.9",
            "langgraph==0.6.4",
            "loguru>=0.7.3",
            "opentelemetry-exporter-otlp-proto-http>=1.36.0",
            "opentelemetry-instrumentation-langchain>=0.45.6",
            "opentelemetry-sdk>=1.36.0",
            "pydantic>=2.11.7",
            "python-dotenv>=1.0.0",
        ],
        extra_packages=["./engine"],
        gcs_dir_name=f"{model}/v{system_prompt_version}/{now}",
        display_name=f"EAI Agent | {model} | v{system_prompt_version}",
        env_vars={
            "PROJECT_ID": env.PROJECT_ID,
            "LOCATION": env.LOCATION,
            "INSTANCE": env.INSTANCE,
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
        },
        service_account=service_account,
        psc_interface_config=psc_config,
    )


if __name__ == "__main__":
    deploy()
