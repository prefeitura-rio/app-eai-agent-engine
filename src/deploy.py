import concurrent.futures
import os
import sys
import time
import uuid
from datetime import datetime, timezone

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


def deploy(deploy_timestamp=None):
    system_prompt = prompt_data["prompt"]
    system_prompt_version = prompt_data["version"]
    model = "gemini-2.5-flash"
    now = deploy_timestamp or datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

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
        display_name=f"EAI Agent | {model} | v{system_prompt_version} | {now}",
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
            "EAI_GATEWAY_API_URL": env.EAI_GATEWAY_API_URL,
            "EAI_GATEWAY_API_TOKEN": env.EAI_GATEWAY_API_TOKEN,
            "SHORT_MEMORY_TOKEN_LIMIT": env.SHORT_MEMORY_TOKEN_LIMIT,
            "SHORT_MEMORY_TIME_LIMIT": env.SHORT_MEMORY_TIME_LIMIT,
            # ENABLE_TTS_ADDENDUM=false força adicionar
            # generate_audio_response a MCP_EXCLUDED_TOOLS, garantindo que o
            # tool binder (engine/agent.py) também o filtre — sem isso o LLM
            # poderia ver a tool schema mesmo com o prompt addendum removido.
            # Mesma logica pra ENABLE_MEDIA_RESPONSE=false + send_whatsapp_media
            # (ADR-022). Codex P2 2026-05-15.
            "MCP_EXCLUDED_TOOLS": ",".join(
                list(env.MCP_EXCLUDED_TOOLS or [])
                + (
                    ["generate_audio_response"]
                    if (env.ENABLE_TTS_ADDENDUM or "true").lower() == "false"
                    and "generate_audio_response" not in (env.MCP_EXCLUDED_TOOLS or [])
                    else []
                )
                + (
                    ["send_whatsapp_media"]
                    if (env.ENABLE_MEDIA_RESPONSE or "true").lower() == "false"
                    and "send_whatsapp_media" not in (env.MCP_EXCLUDED_TOOLS or [])
                    else []
                )
            ),
            "ENABLE_TTS_ADDENDUM": env.ENABLE_TTS_ADDENDUM,
            "ENABLE_MEDIA_RESPONSE": env.ENABLE_MEDIA_RESPONSE,
            "ERROR_INTERCEPTOR_URL": env.ERROR_INTERCEPTOR_URL,
            "ERROR_INTERCEPTOR_TOKEN": env.ERROR_INTERCEPTOR_TOKEN,
        },
        service_account=service_account,
        psc_interface_config=psc_config,
    )


_RECOVERY_POLL_INTERVAL_SECONDS = 30
# Recovery budget capped to fit inside the GH Actions job's `timeout-minutes:
# 45`. The SDK already spent ~15min polling before TimeoutError, so a 15min
# recovery window plus a safety margin keeps the job under the 45min cap.
_RECOVERY_DEADLINE_SECONDS = 15 * 60


def _recover_engine_after_timeout(unique_display_name):
    """Find the engine created by this run when the create poll timed out.

    `agent_engines.create()` blocks polling for up to 900s but the create LRO
    on the GCP side can run longer. The engine still ends up created — we lose
    the synchronous handle. We embed the deploy timestamp into display_name to
    make it run-unique, then poll `agent_engines.list()` until the matching
    resource appears OR the recovery deadline expires.
    """
    deadline = time.monotonic() + _RECOVERY_DEADLINE_SECONDS
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        for engine in agent_engines.list():
            if getattr(engine, "display_name", None) == unique_display_name:
                return engine
        time.sleep(_RECOVERY_POLL_INTERVAL_SECONDS)
    print(
        f"Recovery gave up after {attempts} list attempts over "
        f"{_RECOVERY_DEADLINE_SECONDS}s without finding "
        f'display_name="{unique_display_name}".',
        file=sys.stderr,
    )
    return None


if __name__ == "__main__":
    # Compose a run-unique discriminator so the timeout-recovery list filter
    # can attribute the engine to THIS run, even if a parallel /deploy comment
    # starts a second job for the same prompt version in the same second.
    # GITHUB_RUN_ID is unique per workflow run in CI; outside CI we fall back
    # to a uuid4 prefix so local runs still get a unique tag.
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{uuid.uuid4().hex[:8]}"
    deploy_timestamp = (
        f"{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H_%M_%S')}_{run_id}"
    )
    unique_display_name = (
        f'EAI Agent | gemini-2.5-flash | v{prompt_data["version"]} | {deploy_timestamp}'
    )

    try:
        engine = deploy(deploy_timestamp=deploy_timestamp)
    except concurrent.futures.TimeoutError:
        print(
            "Polling timed out before agent_engines.create() returned. "
            f'Polling agent_engines.list() for display_name="{unique_display_name}" '
            f"every {_RECOVERY_POLL_INTERVAL_SECONDS}s up to {_RECOVERY_DEADLINE_SECONDS}s.",
            file=sys.stderr,
        )
        engine = _recover_engine_after_timeout(unique_display_name)
        if engine is None:
            print(
                "Recovery failed: no engine with the run-unique display_name "
                "appeared within the deadline. The deploy may genuinely have failed.",
                file=sys.stderr,
            )
            raise

    engine_id = engine.resource_name.split("/")[-1]
    print(f"REASONING_ENGINE_ID={engine_id}")
